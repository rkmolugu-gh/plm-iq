"""EdgeConstraintValidator - edge constraint resolution and edge validation as a class.

Why this class exists
---------------------
Edge constraints are DATA (foundation_edge_constraint rows), never hardcoded
constraints; precedence is deterministic per strategy Section 13
(tenant > edition > platform). Wrapping the four operations in one class
gives them a single injectable seam: edge_service composes it, tests can
stub it, and future constraint sources (edition packages, tenant YAML) plug in by
subclassing without touching callers.

Benefits
--------
* Pure domain logic - no module state, fully unit-testable with plain
  mappings; only ``resolve_constraint``/``validate_edge`` touch a Session.
* Precedence table lives beside the resolution logic that consumes it.

How to extend (future scenarios)
-------------------------------
* New scope level -> add a precedence entry + an OR-branch in resolve_constraint.
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


class EdgeConstraintValidator:
    """Resolves the governing edge constraint for an edge pattern and validates
    candidate edges against it."""

    def resolve_constraint(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        edition_id: enums.EditionId,
        edge_kind: enums.EdgeKind,
        source_kind: enums.VertexKind,
        target_kind: enums.VertexKind,
    ) -> dict | None:
        """Return the single governing constraint for an edge pattern, or None."""
        constraint = tables.foundation_edge_constraint.c
        stmt = select(tables.foundation_edge_constraint).where(
            constraint.edge_kind == edge_kind,
            constraint.source_vertex_kind == source_kind,
            constraint.target_vertex_kind == target_kind,
            or_(
                constraint.scope == enums.RuleScope.PLATFORM,
                and_(constraint.scope == enums.RuleScope.EDITION, constraint.edition_id == edition_id),
                and_(constraint.scope == enums.RuleScope.TENANT, constraint.tenant_id == tenant_id),
            ),
        )
        candidates = [dict(r._mapping) for r in session.execute(stmt).all()]
        if not candidates:
            return None
        return max(candidates, key=lambda r: _SCOPE_PRECEDENCE[r["scope"]])

    def check_required_attributes(self, constraint: Mapping, payload: Mapping[str, Any]) -> list[str]:
        """Names in required_edge_attributes missing from the edge payload maps."""
        required = constraint.get("required_edge_attributes") or []
        return [attr for attr in required if attr not in payload or payload[attr] is None]

    def validate_against_constraint(
        self,
        constraint: Mapping,
        *,
        source_lifecycle_state: enums.LifecycleState,
        target_lifecycle_state: enums.LifecycleState,
        annotation: Mapping[str, Any],
        tenant_attributes: Mapping[str, Any],
    ) -> list[str]:
        violations: list[str] = []
        # NULL arrays mean "no restriction"
        allowed_source = set(constraint.get("source_lifecycle_states") or [])
        allowed_target = set(constraint.get("target_lifecycle_states") or [])
        if allowed_source and source_lifecycle_state not in allowed_source:
            violations.append(
                f"source lifecycle state '{source_lifecycle_state.value}' not permitted "
                f"by constraint {constraint['id']}; allowed: {sorted(s.value for s in allowed_source)}"
            )
        if allowed_target and target_lifecycle_state not in allowed_target:
            violations.append(
                f"target lifecycle state '{target_lifecycle_state.value}' not permitted "
                f"by constraint {constraint['id']}; allowed: {sorted(s.value for s in allowed_target)}"
            )
        for attr in self.check_required_attributes(constraint, {**tenant_attributes, **annotation}):
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
        """Resolve + validate; returns (resolved_constraint, violations).

        resolved_constraint is None when no constraint covers the pattern - itself a violation.
        """
        constraint = self.resolve_constraint(
            session,
            tenant_id=tenant_id,
            edition_id=edition_id,
            edge_kind=edge_kind,
            source_kind=source_kind,
            target_kind=target_kind,
        )
        if constraint is None:
            detail = f"no edge constraint governs {edge_kind.value}: {source_kind.value} -> {target_kind.value}"
            logger.warning("edge.validation.no_constraint", extra={"kind": edge_kind.value})
            return None, [detail]
        violations = self.validate_against_constraint(
            constraint,
            source_lifecycle_state=source_lifecycle_state,
            target_lifecycle_state=target_lifecycle_state,
            annotation=annotation,
            tenant_attributes=tenant_attributes,
        )
        if violations:
            logger.warning("edge.validation.violations", extra={
                "kind": edge_kind.value, "count": len(violations),
            })
        return constraint, violations


#: Shared singleton - stateless validator, safe across requests.
edge_validator = EdgeConstraintValidator()
