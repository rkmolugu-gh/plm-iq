"""RuleValidator - graph rule resolution and edge validation as a class.

Why this class exists
---------------------
Graph rules are DATA (foundation_graph_rule rows), never hardcoded
constraints; precedence is deterministic per strategy Section 13
(tenant > edition > platform). Wrapping the four operations in one class
gives them a single injectable seam: edge_service composes it, tests can
stub it, and future rule sources (edition packages, tenant YAML) plug in by
subclassing without touching callers.

Benefits
--------
* Pure domain logic - no module state, fully unit-testable with plain
  mappings; only ``resolve_rule``/``validate_edge`` touch a Session.
* Precedence table lives beside the resolution logic that consumes it.

How to extend (future scenarios)
--------------------------------
* New scope level -> add a precedence entry + an OR-branch in resolve_rule.
* AI-suggested edges (strategy Section 14) -> add a ``suggest()`` method here;
  validation stays authoritative in validate_edge.
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


class RuleValidator:
    """Resolves the governing graph rule for an edge pattern and validates
    candidate edges against it."""

    def resolve_rule(
        self,
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
                and_(rule.scope == enums.RuleScope.EDITION, rule.edition_id == edition_id),
                and_(rule.scope == enums.RuleScope.TENANT, rule.tenant_id == tenant_id),
            ),
        )
        candidates = [dict(r._mapping) for r in session.execute(stmt).all()]
        if not candidates:
            return None
        return max(candidates, key=lambda r: _SCOPE_PRECEDENCE[r["scope"]])

    def check_required_attributes(self, rule: Mapping, payload: Mapping[str, Any]) -> list[str]:
        """Names in required_edge_attributes missing from the edge payload maps."""
        required = rule.get("required_edge_attributes") or []
        return [attr for attr in required if attr not in payload or payload[attr] is None]

    def validate_against_rule(
        self,
        rule: Mapping,
        *,
        source_lifecycle_state: enums.LifecycleState,
        target_lifecycle_state: enums.LifecycleState,
        annotation: Mapping[str, Any],
        tenant_attributes: Mapping[str, Any],
    ) -> list[str]:
        violations: list[str] = []
        # NULL arrays mean "no restriction"
        allowed_source = set(rule.get("source_lifecycle_states") or [])
        allowed_target = set(rule.get("target_lifecycle_states") or [])
        if allowed_source and source_lifecycle_state not in allowed_source:
            violations.append(
                f"source lifecycle state '{source_lifecycle_state.value}' not permitted "
                f"by rule {rule['id']}; allowed: {sorted(s.value for s in allowed_source)}"
            )
        if allowed_target and target_lifecycle_state not in allowed_target:
            violations.append(
                f"target lifecycle state '{target_lifecycle_state.value}' not permitted "
                f"by rule {rule['id']}; allowed: {sorted(s.value for s in allowed_target)}"
            )
        for attr in self.check_required_attributes(rule, {**tenant_attributes, **annotation}):
            violations.append(f"required edge attribute '{attr}' is missing")
        return violations

    def validate_edge(
        self,
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
        """Resolve + validate; returns (resolved_rule, violations).

        resolved_rule is None when no rule covers the pattern - itself a violation.
        """
        rule = self.resolve_rule(
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
        violations = self.validate_against_rule(
            rule,
            source_lifecycle_state=source_lifecycle_state,
            target_lifecycle_state=target_lifecycle_state,
            annotation=annotation,
            tenant_attributes=tenant_attributes,
        )
        if violations:
            logger.warning("edge.validation.violations", extra={
                "kind": edge_kind.value, "count": len(violations),
            })
        return rule, violations


#: Shared singleton - stateless validator, safe across requests.
validator = RuleValidator()
