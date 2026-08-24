"""Provisioning and lifecycle for iam_tenant.

iam_tenant is the cross-tenant workspace registry and deliberately carries no
row-level security (002 isolation notes): it must be readable before a
tenant context exists to resolve subdomains. Callers run these functions via
``db.admin_session()``; access is governed by GRANTs only.
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime as dt
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .errors import Conflict, NotFound, ValidationFailed
from .schemas import Page, TenantCreate, TenantOut, TenantUpdate

logger = logging.getLogger(__name__)

SUBDOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")

TENANT_TRANSITIONS: dict[enums.TenantStatus, frozenset[enums.TenantStatus]] = {
    enums.TenantStatus.PROVISIONING: frozenset({enums.TenantStatus.ACTIVE}),
    enums.TenantStatus.ACTIVE: frozenset({enums.TenantStatus.SUSPENDED}),
    enums.TenantStatus.SUSPENDED: frozenset({enums.TenantStatus.ACTIVE, enums.TenantStatus.ARCHIVED}),
    enums.TenantStatus.ARCHIVED: frozenset(),
}

_UPDATABLE_FIELDS = frozenset({"name", "contact_email", "edition_id", "status"})

_MAX_LIMIT = 200


def _to_out(row) -> TenantOut:
    """DTO mapper that drops the sensitive ``secret`` column."""
    mapping = dict(getattr(row, "_mapping", row))
    mapping.pop("secret", None)
    return TenantOut.model_validate(mapping)


def find_tenant(session: Session, tenant_id: UUID) -> dict | None:
    row = session.execute(select(tables.iam_tenant).where(tables.iam_tenant.c.id == tenant_id)).one_or_none()
    return dict(row._mapping) if row else None


def get_tenant(session: Session, tenant_id: UUID) -> dict:
    tenant = find_tenant(session, tenant_id)
    if tenant is None:
        raise NotFound(f"tenant {tenant_id} not found")
    return tenant


def find_tenant_by_subdomain(session: Session, subdomain: str) -> dict | None:
    row = session.execute(
        select(tables.iam_tenant).where(tables.iam_tenant.c.subdomain == subdomain.lower())
    ).one_or_none()
    return dict(row._mapping) if row else None


def list_tenants(
    session: Session,
    *,
    statuses: list[enums.TenantStatus] | None = None,
    name_like: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[TenantOut]:
    limit = min(max(limit, 1), _MAX_LIMIT)
    offset = max(offset, 0)
    conditions = []
    if statuses:
        conditions.append(tables.iam_tenant.c.status.in_(statuses))
    if name_like:
        conditions.append(tables.iam_tenant.c.name.ilike(f"%{name_like}%"))
    total = session.execute(
        select(func.count()).select_from(tables.iam_tenant).where(*conditions)
    ).scalar_one()
    rows = session.execute(
        select(tables.iam_tenant)
        .where(*conditions)
        .order_by(tables.iam_tenant.c.subdomain)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[TenantOut](
        items=[_to_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def provision_tenant(session: Session, data: TenantCreate, actor: str) -> TenantOut:
    _validate_new_tenant(data)
    values = data.model_dump(exclude_unset=True)
    values.update(created_by=actor, modified_by=actor)
    try:
        row = session.execute(
            insert(tables.iam_tenant).values(**values).returning(*tables.iam_tenant.c)
        ).one()
    except IntegrityError as exc:
        logger.warning("tenant.provision.duplicate", extra={"subdomain": data.subdomain})
        raise Conflict(f"tenant subdomain '{data.subdomain}' or name '{data.name}' already exists") from exc
    logger.info("tenant.provisioned", extra={"tenant": str(row.id), "subdomain": data.subdomain, "actor": actor})
    return _to_out(row)


def update_tenant(session: Session, tenant_id: UUID, data: TenantUpdate, actor: str) -> TenantOut:
    current = get_tenant(session, tenant_id)
    if current["version"] != data.version:
        raise Conflict(
            f"version mismatch on tenant {tenant_id}: expected {data.version}, current {current['version']}"
        )
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    unknown = set(changes) - _UPDATABLE_FIELDS
    if unknown:
        raise ValidationFailed(f"fields not updatable on a tenant: {sorted(unknown)}")
    if current["status"] == enums.TenantStatus.ARCHIVED and changes:
        raise Conflict(f"tenant {tenant_id} is archived and immutable")
    if "contact_email" in changes and "@" not in changes["contact_email"]:
        raise ValidationFailed("contactEmail must contain '@'")
    if "status" in changes:
        _check_transition(tenant_id, current["status"], changes["status"])
    if not changes:
        return _to_out(dict(current))
    row = session.execute(
        update(tables.iam_tenant)
        .where(tables.iam_tenant.c.id == tenant_id, tables.iam_tenant.c.version == data.version)
        .values(**changes, modified_by=actor, modified_on=dt.now())
        .returning(*tables.iam_tenant.c)
    ).one_or_none()
    if row is None:
        refreshed = find_tenant(session, tenant_id)
        if refreshed is None:
            raise NotFound(f"tenant {tenant_id} not found")
        raise Conflict(
            f"concurrent modification on tenant {tenant_id}: expected version {data.version}, "
            f"current {refreshed['version']}"
        )
    logger.info("tenant.updated", extra={"tenant": str(tenant_id), "actor": actor})
    return _to_out(row)


def rotate_secret(
    session: Session, tenant_id: UUID, *, version: int, actor: str, secret: str | None = None
) -> tuple[TenantOut, str]:
    """Replace the tenant integration secret; returns (tenant, new_secret)."""
    new_secret = secret or secrets.token_urlsafe(32)
    current = get_tenant(session, tenant_id)
    if current["status"] == enums.TenantStatus.ARCHIVED:
        raise Conflict(f"tenant {tenant_id} is archived; its secret cannot be rotated")
    row = session.execute(
        update(tables.iam_tenant)
        .where(tables.iam_tenant.c.id == tenant_id, tables.iam_tenant.c.version == version)
        .values(secret=new_secret, modified_by=actor, modified_on=dt.now())
        .returning(*tables.iam_tenant.c)
    ).one_or_none()
    if row is None:
        refreshed = find_tenant(session, tenant_id)
        if refreshed is None:
            raise NotFound(f"tenant {tenant_id} not found")
        raise Conflict(
            f"concurrent modification on tenant {tenant_id}: expected version {version}, "
            f"current {refreshed['version']}"
        )
    logger.info("tenant.secret_rotated", extra={"tenant": str(tenant_id), "actor": actor})
    return _to_out(row), new_secret


def _validate_new_tenant(data: TenantCreate) -> None:
    if not SUBDOMAIN_RE.fullmatch(data.subdomain):
        raise ValidationFailed(
            f"invalid subdomain '{data.subdomain}': must match {SUBDOMAIN_RE.pattern}"
        )
    if "@" not in data.contact_email:
        raise ValidationFailed("contactEmail must contain '@'")


def _check_transition(tenant_id: UUID, old: enums.TenantStatus, new: enums.TenantStatus) -> None:
    allowed = TENANT_TRANSITIONS.get(old, frozenset())
    if new not in allowed:
        raise ValidationFailed(
            f"illegal status transition on tenant {tenant_id}: "
            f"'{old.value}' -> '{new.value}'; allowed next: {sorted(s.value for s in allowed)}"
        )
