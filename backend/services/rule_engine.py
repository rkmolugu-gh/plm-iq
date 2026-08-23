"""Graph rule resolution and validation.

Rules are data (foundation_graph_rule rows), never hardcoded constraints.
Precedence is deterministic per strategy Section 13: the most specific scope
wins — tenant > edition > platform.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from . import enums, tables

logger = logging.getLogger(__name__)

_SCOPE_PRECEDENCE = {
    enums.RuleScope.PLATFORM: 1,
    enums.RuleScope.EDITION: 2,
    enums.RuleScope.TENANT: 3,
}


def resolve_rule(
    session: Session,
    *,
    tenant_id: UUID,
    edition_id: enums.EditionId,
    edge_kind: enums.EdgeKind,
    source_kind: enums.VertexKind,
    target_kind: enums.VertexKind,
) -> dict | None:
    """Return the single governing rule for an edge pattern, or None."""
    rule = tables.foundation_graph_rule.c
    stmt = select(tables.foundation_graph_rule).where(
        rule.edge_kind == edge_kind,
        rule.source_vertex_kind == source_kind,
        rule.target_vertex_kind == target_kind,
        or_(
            rule.scope == enums.RuleScope.PLATFORM,
            and_(
                rule.scope == enums.RuleScope.EDITION,
                rule.edition_id == edition_id,
            ),
            and_(
                rule.scope == enums.RuleScope.TENANT,
                rule.tenant_id == tenant_id,
            ),
        ),
    )
    candidates = [dict(r._mapping) for r in session.execute(stmt).all()]
    if not candidates:
        return None
    return max(candidates, key=lambda r: _SCOPE_PRECEDENCE[r["scope"]])


def check_required_attributes(rule: Mapping, payload: Mapping[str, Any]) -> list[str]:
    """Names in required_edge_attributes missing from the edge payload maps."""
    return [attr for attr in rule["required_edge_attributes"] if attr not in payload or payload[attr] is None]


def validate_against_rule(
    rule: Mapping,
    *,
    source_lifecycle_state: enums.LifecycleState,
    target_lifecycle_state: enums.LifecycleState,
    annotation: Mapping[str, Any],
    tenant_attributes: Mapping[str, Any],
) -> list[str]:
    violations: list[str] = []
    allowed_source = set(rule["source_lifecycle_states"])
    allowed_target = set(rule["target_lifecycle_states"])
    if allowed_source and source_lifecycle_state not in allowed_source:
        violations.append(
            f"source lifecycle state '{source_lifecycle_state.value}' not permitted by rule "
            f"{rule['id']}; allowed: {sorted(s.value for s in allowed_source)}"
        )
    if allowed_target and target_lifecycle_state not in allowed_target:
        violations.append(
            f"target lifecycle state '{target_lifecycle_state.value}' not permitted by rule "
            f"{rule['id']}; allowed: {sorted(s.value for s in allowed_target)}"
        )
    for attr in check_required_attributes(rule, {**tenant_attributes, **annotation}):
        violations.append(f"required edge attribute '{attr}' is missing")
    return violations


def validate_edge(
    session: Session,
    *,
    tenant_id: UUID,
    edition_id: enums.EditionId,
    edge_kind: enums.EdgeKind,
    source_kind: enums.VertexKind,
    target_kind: enums.VertexKind,
    source_lifecycle_state: enums.LifecycleState,
    target_lifecycle_state: enums.LifecycleState,
    annotation: Mapping[str, Any],
    tenant_attributes: Mapping[str, Any],
) -> tuple[dict | None, list[str]]:
    """Resolve the governing rule and validate a candidate edge against it.

    Returns (resolved_rule, violations); resolved_rule is None when no rule
    covers the pattern, which is itself a violation.
    """
    rule = resolve_rule(
        session,
        tenant_id=tenant_id,
        edition_id=edition_id,
        edge_kind=edge_kind,
        source_kind=source_kind,
        target_kind=target_kind,
    )
    if rule is None:
        detail = f"no graph rule governs {edge_kind.value}: {source_kind.value} -> {target_kind.value}"
        logger.warning("edge.validation.no_rule", extra={"kind": edge_kind.value})
        return None, [detail]
    violations = validate_against_rule(
        rule,
        source_lifecycle_state=source_lifecycle_state,
        target_lifecycle_state=target_lifecycle_state,
        annotation=annotation,
        tenant_attributes=tenant_attributes,
    )
    if violations:
        logger.warning(
            "edge.validation.violations",
            extra={"kind": edge_kind.value, "count": len(violations)},
        )
    return rule, violations
