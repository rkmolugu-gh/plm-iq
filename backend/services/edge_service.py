"""EdgeService - CRUD for foundation_edge with rule validation on every write.

Why this class exists
---------------------
Edges are first-class governed entities: every write must resolve the
governing graph rule, enforce effectivity windows, lifecycle transitions,
and duplicate policy. Wrapping those mechanics in one service class keeps
the governance contract in exactly one place; the gateway can never create
an unvalidated edge because it never touches SQL directly.

Benefits
--------
* Inherits shared mechanics (DTO conversion, transition guard) from
  BaseService - no private copies to drift.
* Composes RuleValidator via composition, so rule semantics evolve
  independently of persistence.

How to extend (future scenarios)
--------------------------------
* New edge governance (approval workflows, provenance per metamodel) ->
  add methods here; keep route handlers as thin translators.
* Bulk BOM import -> add ``create_many`` reusing _validate_candidate so
  imported edges obey identical rules.
"""
from __future__ import annotations

import logging
from datetime import date
from datetime import datetime as dt
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .base import BaseService
from .errors import Conflict, NotFound, ValidationFailed
from .edge_constraints import edge_edge_validator
from .schemas import EdgeCreate, EdgeOut, EdgeUpdate, Page, from_row
from .vertex_service import vertices

logger = logging.getLogger(__name__)

_EDGE_TRANSITIONS = {
    enums.EdgeState.PENDING_APPROVAL: frozenset({enums.EdgeState.ACTIVE, enums.EdgeState.INACTIVE}),
    enums.EdgeState.ACTIVE: frozenset({enums.EdgeState.INACTIVE}),
    enums.EdgeState.INACTIVE: frozenset({enums.EdgeState.ACTIVE}),
}

_UPDATABLE_FIELDS = frozenset(
    {"name", "lifecycle_state", "effective_from", "effective_to", "annotation", "tenant_attributes"}
)

_MAX_LIMIT = 200


class EdgeService(BaseService):
    out_model = EdgeOut
    transitions = _EDGE_TRANSITIONS

    # ── reads ────────────────────────────────────────────────────────────────

    def find(self, session: Session, tenant_id: UUID, edge_id: UUID) -> dict | None:
        return self._fetch_one(session, tables.foundation_edge, row_id=edge_id, tenant_id=tenant_id)

    def get(self, session: Session, tenant_id: UUID, edge_id: UUID) -> dict:
        edge = self.find(session, tenant_id, edge_id)
        if edge is None:
            raise NotFound(f"edge {edge_id} not found in tenant {tenant_id}")
        return edge

    def list(
        self,
        session: Session,
        tenant_id: UUID,
        *,
        kinds: list[enums.EdgeKind] | None = None,
        lifecycle_states: list[enums.EdgeState] | None = None,
        source_vertex_id: UUID | None = None,
        target_vertex_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[EdgeOut]:
        limit = min(max(limit, 1), _MAX_LIMIT)
        offset = max(offset, 0)
        conditions = [tables.foundation_edge.c.tenant_id == tenant_id]
        if kinds:
            conditions.append(tables.foundation_edge.c.kind.in_(kinds))
        if lifecycle_states:
            conditions.append(tables.foundation_edge.c.lifecycle_state.in_(lifecycle_states))
        if source_vertex_id:
            conditions.append(tables.foundation_edge.c.source_vertex_id == source_vertex_id)
        if target_vertex_id:
            conditions.append(tables.foundation_edge.c.target_vertex_id == target_vertex_id)
        total = session.execute(
            select(func.count()).select_from(tables.foundation_edge).where(*conditions)
        ).scalar_one()
        rows = session.execute(
            select(tables.foundation_edge)
            .where(*conditions)
            .order_by(tables.foundation_edge.c.created_on, tables.foundation_edge.c.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return Page[EdgeOut](items=[from_row(EdgeOut, r) for r in rows],
                             total=total, limit=limit, offset=offset)

    # ── writes ───────────────────────────────────────────────────────────────

    def create(self, session: Session, tenant_id: UUID, data: EdgeCreate, actor: str) -> EdgeOut:
        if data.source_vertex_id == data.target_vertex_id:
            raise ValidationFailed(
                f"edge '{data.name}' ({data.kind.value}) rejected: source and target must differ"
            )
        self._check_effectivity(data.effective_from, data.effective_to)
        source = self._require_vertex(session, tenant_id, data.source_vertex_id, "source")
        target = self._require_vertex(session, tenant_id, data.target_vertex_id, "target")

        resolved, violations = edge_validator.validate_edge(
            session,
            tenant_id=tenant_id,
            edition_id=data.edition_id,
            edge_kind=data.kind,
            source_kind=data.source_vertex_kind,
            target_kind=data.target_vertex_kind,
            source_lifecycle_state=source["lifecycle_state"],
            target_lifecycle_state=target["lifecycle_state"],
            annotation=data.annotation,
            tenant_attributes=data.tenant_attributes,
        )
        if violations:
            raise ValidationFailed(
                f"edge '{data.name}' ({data.kind.value}: "
                f"{self._vertex_ref(source)} -> {self._vertex_ref(target)}) "
                "rejected by edge constraints",
                details=violations,
            )
        resolved = resolved or {}
        if not resolved.get("duplicate_edges_allowed", False):
            self._reject_duplicate(
                session,
                tenant_id=tenant_id,
                kind=data.kind,
                name=data.name,
                source_vertex_id=data.source_vertex_id,
                target_vertex_id=data.target_vertex_id,
            )
        edge_constraint_id = data.edge_constraint_id or resolved.get("id")

        values = data.model_dump(exclude_unset=True)
        values.update(tenant_id=tenant_id, created_by=actor, modified_by=actor)
        if edge_constraint_id is not None:
            values["edge_constraint_id"] = edge_constraint_id
        try:
            row = session.execute(
                insert(tables.foundation_edge).values(**values).returning(*tables.foundation_edge.c)
            ).one()
        except IntegrityError as exc:
            logger.warning("edge.create.integrity", extra={"tenant": str(tenant_id), "kind": data.kind.value})
            raise Conflict("edge violates a database constraint (duplicate or missing endpoint)") from exc
        logger.info("edge.created", extra={
            "tenant": str(tenant_id), "edge": str(row.id), "kind": data.kind.value,
            "rule": str(edge_constraint_id) if edge_constraint_id else "-", "actor": actor,
        })
        return from_row(EdgeOut, row)

    def update(
        self, session: Session, tenant_id: UUID, edge_id: UUID, data: EdgeUpdate, actor: str
    ) -> EdgeOut:
        current = self.get(session, tenant_id, edge_id)
        if current["version"] != data.version:
            logger.warning("edge.update.stale_version", extra={"edge": str(edge_id)})
            raise Conflict(
                f"version mismatch on edge {edge_id}: expected {data.version}, "
                f"current {current['version']}"
            )
        changes = data.model_dump(exclude_unset=True, exclude={"version"})
        unknown = set(changes) - _UPDATABLE_FIELDS
        if unknown:
            raise ValidationFailed(f"fields not updatable on an edge: {sorted(unknown)}")
        if "lifecycle_state" in changes:
            self._check_transition(
                row_id=edge_id,
                old=current["lifecycle_state"],
                new=changes["lifecycle_state"],
                transitions=_EDGE_TRANSITIONS,
            )
        merged_from = changes.get("effective_from", current["effective_from"])
        merged_to = changes.get("effective_to", current["effective_to"])
        self._check_effectivity(merged_from, merged_to)
        if "annotation" in changes or "tenant_attributes" in changes:
            self._revalidate_required_attributes(
                session,
                tenant_id=tenant_id,
                edition_id=current["edition_id"],
                kind=current["kind"],
                source_kind=current["source_vertex_kind"],
                target_kind=current["target_vertex_kind"],
                stored_constraint_id=current["edge_constraint_id"],
                annotation=changes.get("annotation", current["annotation"]),
                tenant_attributes=changes.get("tenant_attributes", current["tenant_attributes"]),
            )
        if not changes:
            return from_row(EdgeOut, current)
        stmt = (
            update(tables.foundation_edge)
            .where(
                tables.foundation_edge.c.id == edge_id,
                tables.foundation_edge.c.tenant_id == tenant_id,
                tables.foundation_edge.c.version == data.version,
            )
            .values(**changes, modified_by=actor, modified_on=dt.now())
            .returning(*tables.foundation_edge.c)
        )
        row = session.execute(stmt).one_or_none()
        if row is None:
            refreshed = self.find(session, tenant_id, edge_id)
            if refreshed is None:
                raise NotFound(f"edge {edge_id} not found in tenant {tenant_id}")
            raise Conflict(f"concurrent modification on edge {edge_id}; refresh and retry")
        logger.info("edge.updated", extra={
            "tenant": str(tenant_id), "edge": str(edge_id), "actor": actor,
        })
        return from_row(EdgeOut, row)

    def delete(self, session: Session, tenant_id: UUID, edge_id: UUID, *, actor: str) -> None:
        """Remove the relationship row; annotations travel with it (inline JSONB)."""
        edge = self.get(session, tenant_id, edge_id)
        result = session.execute(
            delete(tables.foundation_edge).where(
                tables.foundation_edge.c.id == edge_id,
                tables.foundation_edge.c.tenant_id == tenant_id,
                tables.foundation_edge.c.version == edge["version"],
            )
        )
        if result.rowcount != 1:
            raise Conflict(f"concurrent modification on edge {edge_id}; refresh and retry")
        logger.info("edge.deleted", extra={
            "tenant": str(tenant_id), "edge": str(edge_id), "actor": actor,
        })

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _vertex_ref(vertex: dict) -> str:
        number = f"{vertex['prefix']}-{vertex['number']}" if vertex.get("prefix") else str(vertex.get("number", ""))
        revision = vertex.get("revision") or ""
        return f"{number}/{revision}" if revision else number

    def _require_vertex(self, session: Session, tenant_id: UUID, vertex_id: UUID, role: str) -> dict:
        try:
            return vertices.get(session, tenant_id, vertex_id)
        except NotFound:
            raise NotFound(f"{role} vertex {vertex_id} not found") from None

    @staticmethod
    def _check_effectivity(effective_from: date | None, effective_to: date | None) -> None:
        if effective_from and effective_to and effective_to < effective_from:
            raise ValidationFailed(
                f"invalid effectivity window: effectiveTo ({effective_to}) before "
                f"effectiveFrom ({effective_from})"
            )

    def _reject_duplicate(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        kind: enums.EdgeKind,
        name: str,
        source_vertex_id: UUID,
        target_vertex_id: UUID,
    ) -> None:
        existing = session.execute(
            select(tables.foundation_edge.c.id)
            .where(
                tables.foundation_edge.c.tenant_id == tenant_id,
                tables.foundation_edge.c.kind == kind,
                tables.foundation_edge.c.name == name,
                tables.foundation_edge.c.source_vertex_id == source_vertex_id,
                tables.foundation_edge.c.target_vertex_id == target_vertex_id,
                tables.foundation_edge.c.lifecycle_state.in_(
                    [enums.EdgeState.PENDING_APPROVAL, enums.EdgeState.ACTIVE]
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            raise Conflict(
                f"duplicate {kind.value} relationship '{name}' already exists between these vertices"
            )

    def _revalidate_required_attributes(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        edition_id: enums.EditionId,
        kind: enums.EdgeKind,
        source_kind: enums.VertexKind,
        target_kind: enums.VertexKind,
        stored_constraint_id: UUID | None,
        annotation: dict,
        tenant_attributes: dict,
    ) -> None:
        rule = None
        if stored_constraint_id:
            row = session.execute(
                select(tables.foundation_edge_constraint).where(
                    tables.foundation_edge_constraint.c.id == stored_constraint_id
                )
            ).one_or_none()
            rule = dict(row._mapping) if row else None
        if rule is None:
            resolved = edge_validator.resolve_rule(
                session,
                tenant_id=tenant_id,
                edition_id=edition_id,
                edge_kind=kind,
                source_kind=source_kind,
                target_kind=target_kind,
            )
            if resolved is not None:
                rule = resolved
        if rule is None:
            return
        missing = edge_validator.check_required_attributes(rule, {**tenant_attributes, **annotation})
        if missing:
            raise ValidationFailed(
                "edge rejected by graph rules",
                details=[f"required edge attribute '{attr}' is missing" for attr in missing],
            )


#: Shared singleton for the gateway.
edges = EdgeService()
