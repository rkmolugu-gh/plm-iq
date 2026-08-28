"""EdgeConstraintService - CRUD for foundation_edge_constraint.

Why this class exists
---------------------
Rules are the governance data of the graph engine. Classifying them behind
one service keeps the authorization contract ("tenants author only
scope='tenant' rules; platform/edition rules are read-only") in exactly one
place - enforced here AND by RLS insert/update policies as defense in depth.

Benefits
--------
* Inherits row->DTO conversion from BaseService.
* The ownership guard is a single method every mutation funnels through.

How to extend (future scenarios)
--------------------------------
* Edition packages shipping rules -> extend list() with edition filtering;
  creation stays platform-team-only per strategy Section 12.
* Rule versioning/effective windows -> add columns + methods here; edge
  resolution in RuleValidator picks up precedence automatically.
"""
from __future__ import annotations

import logging
from datetime import datetime as dt
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .base import BaseService
from .errors import Conflict, Forbidden, NotFound, ValidationFailed
from .schemas import EdgeConstraintCreate, EdgeConstraintOut, EdgeConstraintUpdate, Page, from_row

logger = logging.getLogger(__name__)

_UPDATABLE_FIELDS = frozenset(
    {
        "source_cardinality",
        "target_cardinality",
        "source_participation",
        "target_participation",
        "duplicate_edges_allowed",
        "source_lifecycle_states",
        "target_lifecycle_states",
        "required_edge_attributes",
        "allow_tenant_extension",
    }
)

_MAX_LIMIT = 200


class EdgeConstraintService(BaseService):
    out_model = EdgeConstraintOut

    # ── reads ────────────────────────────────────────────────────────────────

    def find(self, session: Session, constraint_id: UUID) -> dict | None:
        return self._fetch_one(session, tables.foundation_edge_constraint, row_id=constraint_id)

    def get(self, session: Session, constraint_id: UUID) -> dict:
        rule = self.find(session, constraint_id)
        if rule is None:
            raise NotFound(f"edge constraint {constraint_id} not found")
        return rule

    def list(
        self,
        session: Session,
        *,
        scopes: list[enums.RuleScope] | None = None,
        edge_kinds: list[enums.EdgeKind] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[EdgeConstraintOut]:
        """List edge constraints visible to the tenant (RLS hides other tenants' rules)."""
        limit = min(max(limit, 1), _MAX_LIMIT)
        offset = max(offset, 0)
        conditions = []
        if scopes:
            conditions.append(tables.foundation_edge_constraint.c.scope.in_(scopes))
        if edge_kinds:
            conditions.append(tables.foundation_edge_constraint.c.edge_kind.in_(edge_kinds))
        total = session.execute(
            select(func.count())
            .select_from(tables.foundation_edge_constraint)
            .where(*conditions)
        ).scalar_one()
        rows = session.execute(
            select(tables.foundation_edge_constraint)
            .where(*conditions)
            .order_by(tables.foundation_edge_constraint.c.created_on)
            .limit(limit)
            .offset(offset)
        ).all()
        return Page[EdgeConstraintOut](items=[from_row(EdgeConstraintOut, r) for r in rows],
                                  total=total, limit=limit, offset=offset)

    # ── writes ───────────────────────────────────────────────────────────────

    def create(self, session: Session, tenant_id: UUID, data: EdgeConstraintCreate, actor: str) -> EdgeConstraintOut:
        if data.scope != enums.RuleScope.TENANT:
            raise Forbidden("tenants may author only edge constraints with scope 'tenant'")
        values = data.model_dump(exclude_unset=True)
        values.update(tenant_id=tenant_id, created_by=actor, modified_by=actor)
        row = session.execute(
            insert(tables.foundation_edge_constraint)
            .values(**values)
            .returning(*tables.foundation_edge_constraint.c)
        ).one()
        logger.info("edge_constraint.created", extra={
            "tenant": str(tenant_id), "constraint": str(row.id), "kind": data.edge_kind.value, "actor": actor,
        })
        return from_row(EdgeConstraintOut, row)

    def update(
        self, session: Session, tenant_id: UUID, constraint_id: UUID, data: EdgeConstraintUpdate, actor: str
    ) -> EdgeConstraintOut:
        current = self._require_own_tenant_constraint(tenant_id, self.get(session, constraint_id))
        if current["version"] != data.version:
            raise Conflict(
                f"version mismatch on edge constraint {constraint_id}: expected {data.version}, "
                f"current {current['version']}"
            )
        changes = data.model_dump(exclude_unset=True, exclude={"version"})
        unknown = set(changes) - _UPDATABLE_FIELDS
        if unknown:
            raise ValidationFailed(f"fields not updatable on an edge constraint: {sorted(unknown)}")
        if not changes:
            return from_row(EdgeConstraintOut, current)
        row = session.execute(
            update(tables.foundation_edge_constraint)
            .where(
                tables.foundation_edge_constraint.c.id == constraint_id,
                tables.foundation_edge_constraint.c.version == data.version,
            )
            .values(**changes, modified_by=actor, modified_on=dt.now())
            .returning(*tables.foundation_edge_constraint.c)
        ).one_or_none()
        if row is None:
            refreshed = self.find(session, constraint_id)
            raise Conflict(f"concurrent modification on edge constraint {constraint_id}" if refreshed
                           else f"edge constraint {constraint_id} not found")
        logger.info("edge_constraint.updated", extra={
            "tenant": str(tenant_id), "constraint": str(constraint_id), "actor": actor,
        })
        return from_row(EdgeConstraintOut, row)

    def delete(self, session: Session, tenant_id: UUID, constraint_id: UUID) -> None:
        self._require_own_tenant_constraint(tenant_id, self.get(session, constraint_id))
        try:
            deleted = session.execute(
                delete(tables.foundation_edge_constraint).where(tables.foundation_edge_constraint.c.id == constraint_id)
            ).rowcount
        except IntegrityError as exc:
            logger.warning("edge_constraint.delete.in_use", extra={"constraint": str(constraint_id)})
            raise Conflict(f"edge constraint {constraint_id} is referenced by edges and cannot be deleted") from exc
        if not deleted:
            raise NotFound(f"edge constraint {constraint_id} not found")
        logger.info("edge_constraint.deleted", extra={"tenant": str(tenant_id), "constraint": str(constraint_id)})

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _require_own_tenant_constraint(tenant_id: UUID, rule: dict) -> dict:
        if rule["scope"] != enums.RuleScope.TENANT or rule["tenant_id"] != tenant_id:
            raise Forbidden("only the owning tenant may modify its own 'tenant' edge constraints")
        return rule


#: Shared singleton for the gateway.
edge_constraints = EdgeConstraintService()
