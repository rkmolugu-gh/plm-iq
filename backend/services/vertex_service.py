"""CRUD and lifecycle transitions for foundation_vertex."""
from __future__ import annotations

import logging
from datetime import date
from datetime import datetime as dt
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .errors import Conflict, NotFound, ValidationFailed
from .schemas import Page, VertexCreate, VertexOut, VertexUpdate, from_row

logger = logging.getLogger(__name__)

VERTEX_TRANSITIONS: dict[enums.LifecycleState, frozenset[enums.LifecycleState]] = {
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


def find_vertex(session: Session, tenant_id: UUID, vertex_id: UUID) -> dict | None:
    row = session.execute(
        select(tables.foundation_vertex).where(
            tables.foundation_vertex.c.id == vertex_id,
            tables.foundation_vertex.c.tenant_id == tenant_id,
        )
    ).one_or_none()
    return dict(row._mapping) if row else None


def get_vertex(session: Session, tenant_id: UUID, vertex_id: UUID) -> dict:
    vertex = find_vertex(session, tenant_id, vertex_id)
    if vertex is None:
        raise NotFound(f"vertex {vertex_id} not found in tenant {tenant_id}")
    return vertex


def list_vertices(
    session: Session,
    tenant_id: UUID,
    *,
    kinds: list[enums.VertexKind] | None = None,
    lifecycle_states: list[enums.LifecycleState] | None = None,
    number_like: str | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Page[VertexOut]:
    limit = min(max(limit, 1), _MAX_LIMIT)
    offset = max(offset, 0)
    conditions = [tables.foundation_vertex.c.tenant_id == tenant_id]
    if not include_deleted:
        conditions.append(tables.foundation_vertex.c.marked_for_deletion.is_(False))
    if kinds:
        conditions.append(tables.foundation_vertex.c.kind.in_(kinds))
    if lifecycle_states:
        conditions.append(tables.foundation_vertex.c.lifecycle_state.in_(lifecycle_states))
    if number_like:
        conditions.append(tables.foundation_vertex.c.number.ilike(f"%{number_like}%"))
    total = session.execute(
        select(func.count()).select_from(tables.foundation_vertex).where(*conditions)
    ).scalar_one()
    rows = session.execute(
        select(tables.foundation_vertex)
        .where(*conditions)
        .order_by(tables.foundation_vertex.c.number, tables.foundation_vertex.c.revision)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[VertexOut](
        items=[from_row(VertexOut, r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def create_vertex(session: Session, tenant_id: UUID, data: VertexCreate, actor: str) -> VertexOut:
    values = data.model_dump(exclude_unset=True)
    values.update(tenant_id=tenant_id, created_by=actor, modified_by=actor)
    try:
        row = session.execute(
            insert(tables.foundation_vertex).values(**values).returning(*tables.foundation_vertex.c)
        ).one()
    except IntegrityError as exc:
        logger.warning("vertex.create.duplicate", extra={"tenant": str(tenant_id)})
        raise Conflict(
            f"vertex number '{data.prefix}-{data.number}' revision '{data.revision}' already exists"
        ) from exc
    logger.info("vertex.created", extra={"tenant": str(tenant_id), "vertex": str(row.id), "actor": actor})
    return from_row(VertexOut, row)


def update_vertex(
    session: Session, tenant_id: UUID, vertex_id: UUID, data: VertexUpdate, actor: str
) -> VertexOut:
    current = get_vertex(session, tenant_id, vertex_id)
    if current["version"] != data.version:
        logger.warning("vertex.update.stale_version", extra={"vertex": str(vertex_id)})
        raise Conflict(
            f"version mismatch on vertex {vertex_id}: expected {data.version}, current {current['version']}"
        )
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    unknown = set(changes) - _UPDATABLE_FIELDS
    if unknown:
        raise ValidationFailed(f"fields not updatable on a vertex: {sorted(unknown)}")
    if current["lifecycle_state"] == enums.LifecycleState.RELEASED and changes:
        raise Conflict(
            f"vertex {vertex_id} is Released and immutable; supersede it or route through change management"
        )
    if not changes:
        return from_row(VertexOut, dict(current))
    if "lifecycle_state" in changes:
        _check_transition(vertex_id, current["lifecycle_state"], changes["lifecycle_state"])
        if changes["lifecycle_state"] == enums.LifecycleState.RELEASED and changes.get("release_on") is None:
            changes["release_on"] = date.today()
    updated = _execute_versioned_update(
        session,
        tables.foundation_vertex,
        changes,
        vertex_id=vertex_id,
        tenant_id=tenant_id,
        expected_version=data.version,
        actor=actor,
    )
    logger.info("vertex.updated", extra={"tenant": str(tenant_id), "vertex": str(vertex_id), "actor": actor})
    return from_row(VertexOut, updated)


def soft_delete_vertex(
    session: Session, tenant_id: UUID, vertex_id: UUID, *, version: int, actor: str
) -> VertexOut:
    current = get_vertex(session, tenant_id, vertex_id)
    if current["lifecycle_state"] == enums.LifecycleState.RELEASED:
        raise Conflict(f"vertex {vertex_id} is Released; deletion requires supersession or change approval")
    updated = _execute_versioned_update(
        session,
        tables.foundation_vertex,
        {"marked_for_deletion": True},
        vertex_id=vertex_id,
        tenant_id=tenant_id,
        expected_version=version,
        actor=actor,
    )
    logger.info("vertex.soft_deleted", extra={"tenant": str(tenant_id), "vertex": str(vertex_id), "actor": actor})
    return from_row(VertexOut, updated)


def _check_transition(vertex_id: UUID, old: enums.LifecycleState, new: enums.LifecycleState) -> None:
    allowed = VERTEX_TRANSITIONS.get(old, frozenset())
    if new not in allowed:
        raise ValidationFailed(
            f"illegal lifecycle transition on vertex {vertex_id}: "
            f"'{old.value}' -> '{new.value}'; allowed next: {sorted(s.value for s in allowed)}"
        )


def _execute_versioned_update(
    session: Session,
    table,
    changes: dict,
    *,
    vertex_id: UUID,
    tenant_id: UUID,
    expected_version: int,
    actor: str,
):
    stmt = (
        update(table)
        .where(table.c.id == vertex_id, table.c.tenant_id == tenant_id, table.c.version == expected_version)
        .values(**changes, modified_by=actor, modified_on=dt.now())
        .returning(*table.c)
    )
    row = session.execute(stmt).one_or_none()
    if row is None:
        refreshed = find_vertex(session, tenant_id, vertex_id)
        if refreshed is None:
            raise NotFound(f"vertex {vertex_id} not found in tenant {tenant_id}")
        logger.warning("vertex.update.race_lost", extra={"vertex": str(vertex_id)})
        raise Conflict(
            f"concurrent modification on vertex {vertex_id}: expected version {expected_version}, "
            f"current {refreshed['version']}"
        )
    return row
