"""VertexCoreService - the shared engine behind every vertex subtype.

Why this class exists
---------------------
This is the OOP realization of the TSE pattern (strategy Section 8). ONE
class owns everything that makes a row a *vertex* - numbering, uniqueness,
revisions, lifecycle transitions, optimistic locking, soft delete, paged
listing - parameterized by class attributes instead of copy-pasted per
subtype. Subtypes inherit ~90% of their backend and add only genuinely new
capabilities (see document_service.DocumentService).

Benefits
--------
* A new business type (PartService, ECService, ...) is a ~20-line subclass:
  pin ``kind``/DTOs/extension table and you get full CRUD + numbering.
* Numbering pools are scoped automatically: an instance with ``kind`` set
  never draws from (or leaks into) another kind's pool; the shared
  ``vertices`` instance draws across all kinds.
* Optimistic locking and lifecycle rules live in exactly one place.

How to extend (future scenarios)
--------------------------------
::

    class PartService(VertexCoreService):
        kind = VertexKind.PART
        out_model = PartOut                      # DocumentOut-style subclass
        create_model = PartCreate
        extension_table = tables.foundation_part  # TSE extension table
        ext_columns = [func.coalesce(...)...]     # flat-row projection

Reads become LEFT JOINs over the extension table with COALESCEd defaults, so
"no extension row yet" behaves as documented in strategy Section 8. Override
``create()`` for multi-phase writes (see DocumentService) and call
``super().create()`` inside your own transaction-safe orchestration.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .base import BaseService
from .errors import Conflict, NotFound, ValidationFailed
from .schemas import Page, VertexCreate, VertexOut, VertexUpdate

logger = logging.getLogger(__name__)

_VERTEX_TRANSITIONS = {
    enums.LifecycleState.DRAFT: frozenset({enums.LifecycleState.IN_REVIEW}),
    enums.LifecycleState.IN_REVIEW: frozenset({enums.LifecycleState.APPROVED}),
    enums.LifecycleState.APPROVED: frozenset({enums.LifecycleState.RELEASED}),
    enums.LifecycleState.RELEASED: frozenset(
        {enums.LifecycleState.SUPERSEDED, enums.LifecycleState.OBSOLETE}
    ),
    enums.LifecycleState.SUPERSEDED: frozenset({enums.LifecycleState.OBSOLETE}),
    enums.LifecycleState.OBSOLETE: frozenset(),
}

_UPDATABLE_FIELDS = frozenset(
    {
        "name",
        "description",
        "classification_id",
        "solution_attributes",
        "tenant_attributes",
        "revision",
        "lifecycle_state",
        "release_on",
    }
)

_MAX_LIMIT = 200

_NUMERIC_RE = re.compile(r"^\d+$")
_ALPHA_RE = re.compile(r"^[A-Z]+$")


def increment_revision(last: str) -> str:
    """Successor of a revision identifier ('A'->'B', 'Z'->'AA', '009'->'010').

    Module-level on purpose: pure vocabulary logic with no I/O, reusable by
    importers, migrations, and tests without instantiating a service.
    """
    last = (last or "").strip()
    if not last:
        return "A"
    if _NUMERIC_RE.match(last):
        return str(int(last) + 1).zfill(len(last))
    if _ALPHA_RE.match(last):
        chars = list(last)
        for i in range(len(chars) - 1, -1, -1):
            if chars[i] != "Z":
                chars[i] = chr(ord(chars[i]) + 1)
                break
            chars[i] = "A"
            if i == 0:
                chars.insert(0, "A")
        return "".join(chars)
    raise ValidationFailed(f"cannot auto-increment revision '{last}'; set it manually")


class VertexCoreService(BaseService):
    """CRUD/lifecycle/numbering engine for foundation_vertex rows."""

    kind: enums.VertexKind | None = None
    out_model = VertexOut
    create_model = VertexCreate
    update_model = VertexUpdate
    transitions = _VERTEX_TRANSITIONS
    updatable_fields = _UPDATABLE_FIELDS

    #: TSE extension table + its projected columns (set by subtypes only).
    extension_table: Any = None
    ext_columns: tuple = ()

    sortable: dict[str, Any] = {
        "number": tables.foundation_vertex.c.number,
        "name": tables.foundation_vertex.c.name,
        "revision": tables.foundation_vertex.c.revision,
        "state": tables.foundation_vertex.c.lifecycle_state,
        "modified": tables.foundation_vertex.c.modified_on,
    }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Copy-per-subclass so subtypes extending these mappings can never
        # mutate the base (or a sibling's) dictionaries.
        cls.sortable = dict(cls.sortable)
        cls.ext_columns = tuple(cls.ext_columns)

    # ── selection plumbing ───────────────────────────────────────────────────

    def _core_cols(self):
        return [c for c in tables.foundation_vertex.c]

    def _ext_cols(self):
        return list(self.ext_columns)

    def _flat_select(self, session: Session):
        stmt = select(*self._core_cols(), *self._ext_cols())
        if self.extension_table is not None:
            stmt = stmt.join(self.extension_table, self.extension_table.c.id ==
                             tables.foundation_vertex.c.id, isouter=True)
        return stmt

    def _kind_conditions(self, kinds: list | None = None) -> list:
        conditions = []
        if self.kind is not None:
            # Implicit hard scoping: a pinned service NEVER sees other kinds,
            # regardless of what a caller passes.
            conditions.append(tables.foundation_vertex.c.kind == self.kind)
            if kinds and any(k != self.kind for k in kinds):
                raise ValidationFailed(
                    f"{type(self).__name__} only handles kind='{self.kind.value}'"
                )
        elif kinds:
            conditions.append(tables.foundation_vertex.c.kind.in_(kinds))
        return conditions

    # ── reads ────────────────────────────────────────────────────────────────

    def find(self, session: Session, tenant_id: UUID, vertex_id: UUID) -> dict | None:
        row = session.execute(
            self._flat_select(session).where(
                tables.foundation_vertex.c.id == vertex_id,
                tables.foundation_vertex.c.tenant_id == tenant_id,
            )
        ).one_or_none()
        return dict(row._mapping) if row else None

    def get(self, session: Session, tenant_id: UUID, vertex_id: UUID) -> dict:
        vertex = self.find(session, tenant_id, vertex_id)
        if vertex is None:
            raise NotFound(f"vertex {vertex_id} not found in tenant {tenant_id}")
        return vertex

    def list(
        self,
        session: Session,
        tenant_id: UUID,
        *,
        number_like: str | None = None,
        kinds: list[enums.VertexKind] | None = None,
        lifecycle_states: list[enums.LifecycleState] | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
        sort: str = "number",
        direction: str = "asc",
    ) -> Page:
        limit = min(max(limit, 1), _MAX_LIMIT)
        offset = max(offset, 0)
        conditions = [tables.foundation_vertex.c.tenant_id == tenant_id]
        conditions.extend(self._kind_conditions(kinds))
        if not include_deleted:
            conditions.append(tables.foundation_vertex.c.marked_for_deletion.is_(False))
        if number_like:
            conditions.append(tables.foundation_vertex.c.number.ilike(f"%{number_like}%"))
        if lifecycle_states:
            conditions.append(tables.foundation_vertex.c.lifecycle_state.in_(lifecycle_states))

        order_col = self.sortable.get(sort, tables.foundation_vertex.c.number)
        order = order_col.desc() if direction == "desc" else order_col.asc()

        total = session.execute(
            select(func.count())
            .select_from(tables.foundation_vertex)
            .join(
                self.extension_table,
                self.extension_table.c.id == tables.foundation_vertex.c.id,
                isouter=True,
            )
            .where(*conditions)
        ).scalar_one() if self.extension_table is not None else session.execute(
            select(func.count()).select_from(tables.foundation_vertex).where(*conditions)
        ).scalar_one()

        rows = session.execute(
            self._flat_select(session)
            .where(*conditions)
            .order_by(order, tables.foundation_vertex.c.number.asc(),
                      tables.foundation_vertex.c.revision.asc())
            .limit(limit)
            .offset(offset)
        ).all()
        return Page[self.out_model](  # type: ignore[name-defined]
            items=[self._to_out(r) for r in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    # ── writes ───────────────────────────────────────────────────────────────

    def create(self, session: Session, tenant_id: UUID, data: VertexCreate, actor: str) -> VertexOut:
        # FULL dump (not exclude_unset): DTO defaults mirror DB defaults, so
        # sending every declared field kills the NotNullViolation-on-defaulted-
        # required-column bug class permanently. Partial semantics belong to
        # update(), where they are genuinely needed.
        values = data.model_dump()
        values.update(tenant_id=tenant_id, created_by=actor, modified_by=actor)
        try:
            row = session.execute(
                insert(tables.foundation_vertex).values(**values).returning(
                    tables.foundation_vertex.c.id
                )
            ).one()
        except IntegrityError as exc:
            logger.warning("vertex.create.duplicate", extra={"tenant": str(tenant_id)})
            raise Conflict(
                f"vertex number '{data.prefix}-{data.number}' revision "
                f"'{data.revision}' already exists"
            ) from exc
        logger.info("vertex.created", extra={
            "tenant": str(tenant_id), "number": f"{data.prefix}-{data.number}", "actor": actor,
        })
        return self.get_out(session, tenant_id, row.id)

    def get_out(self, session: Session, tenant_id: UUID, vertex_id: UUID):
        """Validated Out DTO from the joined flat row (hook point for types)."""
        return self._to_out(self.get(session, tenant_id, vertex_id))

    def update(
        self,
        session: Session,
        tenant_id: UUID,
        vertex_id: UUID,
        data: VertexUpdate,
        actor: str,
    ) -> VertexOut:
        current = self.get(session, tenant_id, vertex_id)
        if current["version"] != data.version:
            logger.warning("vertex.update.stale_version", extra={"vertex": str(vertex_id)})
            raise Conflict(
                f"version mismatch on vertex {vertex_id}: expected {data.version}, "
                f"current {current['version']}"
            )
        changes = data.model_dump(exclude_unset=True, exclude={"version"})
        unknown = set(changes) - self.updatable_fields
        if unknown:
            raise ValidationFailed(f"fields not updatable on a vertex: {sorted(unknown)}")
        if current["lifecycle_state"] == enums.LifecycleState.RELEASED and changes:
            raise Conflict(
                f"vertex {vertex_id} is Released and immutable; supersede it or "
                "route through change management"
            )
        if "lifecycle_state" in changes:
            self._check_transition(
                row_id=vertex_id, old=current["lifecycle_state"], new=changes["lifecycle_state"]
            )
            if changes["lifecycle_state"] == enums.LifecycleState.RELEASED and changes.get("release_on") is None:
                changes["release_on"] = date.today()
        if not changes:
            return self._to_out(current)
        updated = self._versioned_update(
            session,
            tables.foundation_vertex,
            changes,
            row_id=vertex_id,
            tenant_id=tenant_id,
            expected_version=data.version,
            actor=actor,
        )
        logger.info("vertex.updated", extra={
            "tenant": str(tenant_id), "vertex": str(vertex_id), "actor": actor,
        })
        return self._to_out(updated)

    def soft_delete(self, session: Session, tenant_id: UUID, vertex_id: UUID, *, version: int, actor: str):
        current = self.get(session, tenant_id, vertex_id)
        if current["lifecycle_state"] == enums.LifecycleState.RELEASED:
            raise Conflict(
                f"vertex {vertex_id} is Released; deletion requires supersession or change approval"
            )
        updated = self._versioned_update(
            session,
            tables.foundation_vertex,
            {"marked_for_deletion": True},
            row_id=vertex_id,
            tenant_id=tenant_id,
            expected_version=version,
            actor=actor,
        )
        logger.info("vertex.soft_deleted", extra={
            "tenant": str(tenant_id), "vertex": str(vertex_id), "actor": actor,
        })
        return self._to_out(updated)

    # ── numbering ────────────────────────────────────────────────────────────

    def next_number(self, session: Session, tenant_id: UUID, *, prefix: str) -> str:
        """Next free business number for a prefix: max(numeric)+1, padded to >=4."""
        conditions = [
            tables.foundation_vertex.c.tenant_id == tenant_id,
            tables.foundation_vertex.c.prefix == prefix,
            tables.foundation_vertex.c.marked_for_deletion.is_(False),
        ]
        conditions.extend(self._kind_conditions())
        numbers = session.execute(
            select(tables.foundation_vertex.c.number).where(*conditions)
        ).scalars().all()
        numerics = [n for n in numbers if _NUMERIC_RE.match(n)]
        if not numerics:
            return "1001"
        width = max(4, max(len(n) for n in numerics))
        return str(max(int(n) for n in numerics) + 1).zfill(width)

    def next_revision(self, session: Session, tenant_id: UUID, *, prefix: str, number: str) -> str:
        """Revision following the highest stored one for {prefix}-{number}."""
        conditions = [
            tables.foundation_vertex.c.tenant_id == tenant_id,
            tables.foundation_vertex.c.prefix == prefix,
            tables.foundation_vertex.c.number == number,
        ]
        conditions.extend(self._kind_conditions())

        def rank(value: str) -> tuple[int, int]:
            if _NUMERIC_RE.match(value):
                return (0, int(value))
            if _ALPHA_RE.match(value):
                total = 0
                for ch in value:
                    total = total * 26 + (ord(ch) - ord("A") + 1)
                return (1, total)
            return (-1, 0)

        revisions = session.execute(
            select(tables.foundation_vertex.c.revision).where(*conditions)
        ).scalars().all()
        meaningful = [r for r in revisions if r]
        if not meaningful:
            return "A"
        return increment_revision(max(meaningful, key=rank))


#: Shared, kind-neutral instance: the graph explorer and cross-kind tooling
#: use this one. Subtypes expose their own pinned instances.
vertices = VertexCoreService()
