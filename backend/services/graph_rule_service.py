"""CRUD for foundation_graph_rule.

Tenants author only scope='tenant' rules; platform and edition rules are
read-only (enforced here and by RLS insert/update policies).
"""
from __future__ import annotations

import logging
from datetime import datetime as dt
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .errors import Conflict, Forbidden, NotFound, ValidationFailed
from .schemas import GraphRuleCreate, GraphRuleOut, GraphRuleUpdate, Page, from_row

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


def find_rule(session: Session, rule_id: UUID) -> dict | None:
    row = session.execute(
        select(tables.foundation_graph_rule).where(tables.foundation_graph_rule.c.id == rule_id)
    ).one_or_none()
    return dict(row._mapping) if row else None


def get_rule(session: Session, rule_id: UUID) -> dict:
    rule = find_rule(session, rule_id)
    if rule is None:
        raise NotFound(f"graph rule {rule_id} not found")
    return rule


def list_rules(
    session: Session,
    *,
    scopes: list[enums.RuleScope] | None = None,
    edge_kinds: list[enums.EdgeKind] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[GraphRuleOut]:
    """List rules visible to the tenant (RLS hides other tenants' rules)."""
    limit = min(max(limit, 1), _MAX_LIMIT)
    offset = max(offset, 0)
    conditions = []
    if scopes:
        conditions.append(tables.foundation_graph_rule.c.scope.in_(scopes))
    if edge_kinds:
        conditions.append(tables.foundation_graph_rule.c.edge_kind.in_(edge_kinds))
    base = select(tables.foundation_graph_rule)
    total = session.execute(
        select(func.count())
        .select_from(tables.foundation_graph_rule)
        .where(*conditions)
    ).scalar_one()
    rows = session.execute(
        base.where(*conditions).order_by(tables.foundation_graph_rule.c.created_on).limit(limit).offset(offset)
    ).all()
    return Page[GraphRuleOut](
        items=[from_row(GraphRuleOut, r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def create_rule(session: Session, tenant_id: UUID, data: GraphRuleCreate, actor: str) -> GraphRuleOut:
    if data.scope != enums.RuleScope.TENANT:
        raise Forbidden("tenants may author only rules with scope 'tenant'")
    values = data.model_dump(exclude_unset=True)
    values.update(tenant_id=tenant_id, created_by=actor, modified_by=actor)
    row = session.execute(
        insert(tables.foundation_graph_rule)
        .values(**values)
        .returning(*tables.foundation_graph_rule.c)
    ).one()
    logger.info(
        "graph_rule.created",
        extra={"tenant": str(tenant_id), "rule": str(row.id), "kind": data.edge_kind.value, "actor": actor},
    )
    return from_row(GraphRuleOut, row)


def update_rule(
    session: Session, tenant_id: UUID, rule_id: UUID, data: GraphRuleUpdate, actor: str
) -> GraphRuleOut:
    current = _require_own_tenant_rule(tenant_id, get_rule(session, rule_id))
    if current["version"] != data.version:
        raise Conflict(
            f"version mismatch on graph rule {rule_id}: expected {data.version}, current {current['version']}"
        )
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    unknown = set(changes) - _UPDATABLE_FIELDS
    if unknown:
        raise ValidationFailed(f"fields not updatable on a graph rule: {sorted(unknown)}")
    if not changes:
        return from_row(GraphRuleOut, current)
    row = session.execute(
        update(tables.foundation_graph_rule)
        .where(
            tables.foundation_graph_rule.c.id == rule_id,
            tables.foundation_graph_rule.c.version == data.version,
        )
        .values(**changes, modified_by=actor, modified_on=dt.now())
        .returning(*tables.foundation_graph_rule.c)
    ).one_or_none()
    if row is None:
        refreshed = find_rule(session, rule_id)
        raise Conflict(f"concurrent modification on graph rule {rule_id}" if refreshed else f"graph rule {rule_id} not found")
    logger.info("graph_rule.updated", extra={"tenant": str(tenant_id), "rule": str(rule_id), "actor": actor})
    return from_row(GraphRuleOut, row)


def delete_rule(session: Session, tenant_id: UUID, rule_id: UUID) -> None:
    _require_own_tenant_rule(tenant_id, get_rule(session, rule_id))
    try:
        deleted = session.execute(
            delete(tables.foundation_graph_rule).where(tables.foundation_graph_rule.c.id == rule_id)
        ).rowcount
    except IntegrityError as exc:
        logger.warning("graph_rule.delete.in_use", extra={"rule": str(rule_id)})
        raise Conflict(f"graph rule {rule_id} is referenced by edges and cannot be deleted") from exc
    if not deleted:
        raise NotFound(f"graph rule {rule_id} not found")
    logger.info("graph_rule.deleted", extra={"tenant": str(tenant_id), "rule": str(rule_id)})


def _require_own_tenant_rule(tenant_id: UUID, rule: dict) -> dict:
    if rule["scope"] != enums.RuleScope.TENANT or rule["tenant_id"] != tenant_id:
        raise Forbidden("only the owning tenant may modify its own 'tenant' rules")
    return rule
