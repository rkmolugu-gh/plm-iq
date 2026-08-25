"""Tenant-scoped user account management for iam_user.

Every function runs inside ``tenant_session(tenant_id)``; row-level security
plus the tenant_id predicates below keep accounts isolated per workspace.
Email is the globally unique login identifier (lower(email) index in 002)
and accepts either an email address or a bare login id such as 'plm-iq'.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime as dt
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .errors import Conflict, NotFound, ValidationFailed
from .schemas import Page, UserCreate, UserOut, UserUpdate

logger = logging.getLogger(__name__)

# Bare login ids (no '@') mirror the ck_user_email check in 002.
LOGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

USER_TRANSITIONS: dict[enums.UserStatus, frozenset[enums.UserStatus]] = {
    enums.UserStatus.ACTIVE: frozenset({enums.UserStatus.DISABLED, enums.UserStatus.LOCKED}),
    enums.UserStatus.DISABLED: frozenset({enums.UserStatus.ACTIVE}),
    enums.UserStatus.LOCKED: frozenset({enums.UserStatus.ACTIVE, enums.UserStatus.DISABLED}),
}

_UPDATABLE_FIELDS = frozenset(
    {"full_name", "is_tenant_admin", "password_hash", "mfa_enabled", "status"}
)

_MAX_LIMIT = 200


def _to_out(row) -> UserOut:
    """DTO mapper that drops the sensitive ``password_hash`` column."""
    mapping = dict(getattr(row, "_mapping", row))
    mapping.pop("password_hash", None)
    return UserOut.model_validate(mapping)


def find_user_by_login(session: Session, login_id: str) -> dict | None:
    """Resolve a globally unique login id (email or bare id) to a user.

    Login happens before any tenant is known, so callers must run this via
    ``db.admin_session()`` — iam_user's RLS policy would otherwise deny every
    row. Verify ``password_hash`` with bcrypt before trusting the result.
    """
    row = session.execute(
        select(tables.iam_user).where(func.lower(tables.iam_user.c.email) == login_id.strip().lower())
    ).one_or_none()
    return dict(row._mapping) if row else None


def find_user(session: Session, tenant_id: UUID, user_id: UUID) -> dict | None:
    row = session.execute(
        select(tables.iam_user).where(
            tables.iam_user.c.id == user_id,
            tables.iam_user.c.tenant_id == tenant_id,
        )
    ).one_or_none()
    return dict(row._mapping) if row else None


def get_user(session: Session, tenant_id: UUID, user_id: UUID) -> dict:
    user = find_user(session, tenant_id, user_id)
    if user is None:
        raise NotFound(f"user {user_id} not found in tenant {tenant_id}")
    return user


def list_users(
    session: Session,
    tenant_id: UUID,
    *,
    statuses: list[enums.UserStatus] | None = None,
    email_like: str | None = None,
    admins_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Page[UserOut]:
    limit = min(max(limit, 1), _MAX_LIMIT)
    offset = max(offset, 0)
    conditions = [tables.iam_user.c.tenant_id == tenant_id]
    if statuses:
        conditions.append(tables.iam_user.c.status.in_(statuses))
    if email_like:
        conditions.append(tables.iam_user.c.email.ilike(f"%{email_like}%"))
    if admins_only:
        conditions.append(tables.iam_user.c.is_tenant_admin.is_(True))
    total = session.execute(
        select(func.count()).select_from(tables.iam_user).where(*conditions)
    ).scalar_one()
    rows = session.execute(
        select(tables.iam_user)
        .where(*conditions)
        .order_by(tables.iam_user.c.created_on, tables.iam_user.c.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[UserOut](
        items=[_to_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def create_user(session: Session, tenant_id: UUID, data: UserCreate, actor: str) -> UserOut:
    if "@" not in data.email and not LOGIN_ID_RE.fullmatch(data.email):
        raise ValidationFailed(
            f"invalid login id '{data.email}': must be an email address or match {LOGIN_ID_RE.pattern}"
        )
    values = data.model_dump(exclude_unset=True)
    values.update(tenant_id=tenant_id, created_by=actor, modified_by=actor)
    try:
        row = session.execute(insert(tables.iam_user).values(**values).returning(*tables.iam_user.c)).one()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
        logger.warning("user.create.integrity", extra={"tenant": str(tenant_id), "constraint": constraint})
        if "tenant" in constraint:
            raise Conflict(f"tenant {tenant_id} does not exist") from exc
        raise Conflict(f"a user with email '{data.email}' already exists") from exc
    logger.info("user.created", extra={"tenant": str(tenant_id), "user": str(row.id), "actor": actor})
    return _to_out(row)


def update_user(session: Session, tenant_id: UUID, user_id: UUID, data: UserUpdate, actor: str) -> UserOut:
    current = get_user(session, tenant_id, user_id)
    if current["version"] != data.version:
        raise Conflict(
            f"version mismatch on user {user_id}: expected {data.version}, current {current['version']}"
        )
    changes = data.model_dump(exclude_unset=True, exclude={"version"})
    unknown = set(changes) - _UPDATABLE_FIELDS
    if unknown:
        raise ValidationFailed(f"fields not updatable on a user: {sorted(unknown)}")
    if "status" in changes:
        _check_transition(user_id, current["status"], changes["status"])
    if not changes:
        return _to_out(dict(current))
    updated = _execute_versioned_update(
        session,
        changes,
        user_id=user_id,
        tenant_id=tenant_id,
        expected_version=data.version,
        actor=actor,
    )
    logger.info("user.updated", extra={"tenant": str(tenant_id), "user": str(user_id), "actor": actor})
    return _to_out(updated)


def list_users_outside_tenant(session: Session, tenant_id: UUID, *, limit: int = 200) -> list[UserOut]:
    """Accounts NOT in the given tenant — candidates for 'add existing user'.

    Cross-tenant read: run via ``db.admin_session()``.
    """
    rows = session.execute(
        select(tables.iam_user)
        .where(tables.iam_user.c.tenant_id != tenant_id)
        .order_by(tables.iam_user.c.email)
        .limit(min(max(limit, 1), _MAX_LIMIT))
    ).all()
    return [_to_out(r) for r in rows]


def assign_user_to_tenant(session: Session, target_tenant_id: UUID, login_id: str, actor: str) -> UserOut:
    """Move an existing account into the target tenant.

    Platform-level operation (cross-tenant): run via ``db.admin_session()``.
    The account keeps its id, credentials, and role-assignment rows; only
    its tenant membership changes. Version bumps via the identity trigger.
    """
    row = session.execute(
        select(tables.iam_user).where(func.lower(tables.iam_user.c.email) == login_id.strip().lower())
    ).one_or_none()
    if row is None:
        raise NotFound(f"user '{login_id}' not found")
    if row.tenant_id == target_tenant_id:
        raise ValidationFailed(f"user '{login_id}' already belongs to this tenant")
    updated = session.execute(
        update(tables.iam_user)
        .where(tables.iam_user.c.id == row.id)
        .values(tenant_id=target_tenant_id, modified_by=actor, modified_on=dt.now())
        .returning(*tables.iam_user.c)
    ).one()
    logger.info(
        "user.tenant_assigned",
        extra={"tenant": str(target_tenant_id), "user": str(row.id), "actor": actor},
    )
    return _to_out(updated)


def record_login(session: Session, tenant_id: UUID, user_id: UUID, *, actor: str | None = None) -> UserOut:
    """Stamp last_login_on after a successful authentication.

    Deliberately skips the version guard: the login flow has no prior read to
    race against and must never fail because an admin edited the profile.
    """
    row = session.execute(
        update(tables.iam_user)
        .where(tables.iam_user.c.id == user_id, tables.iam_user.c.tenant_id == tenant_id)
        .values(last_login_on=dt.now(), modified_by=actor or "system", modified_on=dt.now())
        .returning(*tables.iam_user.c)
    ).one_or_none()
    if row is None:
        raise NotFound(f"user {user_id} not found in tenant {tenant_id}")
    logger.info("user.login_recorded", extra={"tenant": str(tenant_id), "user": str(user_id)})
    return _to_out(row)


def _check_transition(user_id: UUID, old: enums.UserStatus, new: enums.UserStatus) -> None:
    allowed = USER_TRANSITIONS.get(old, frozenset())
    if new not in allowed:
        raise ValidationFailed(
            f"illegal status transition on user {user_id}: "
            f"'{old.value}' -> '{new.value}'; allowed next: {sorted(s.value for s in allowed)}"
        )


def _execute_versioned_update(
    session: Session,
    changes: dict,
    *,
    user_id: UUID,
    tenant_id: UUID,
    expected_version: int,
    actor: str,
):
    stmt = (
        update(tables.iam_user)
        .where(
            tables.iam_user.c.id == user_id,
            tables.iam_user.c.tenant_id == tenant_id,
            tables.iam_user.c.version == expected_version,
        )
        .values(**changes, modified_by=actor, modified_on=dt.now())
        .returning(*tables.iam_user.c)
    )
    row = session.execute(stmt).one_or_none()
    if row is None:
        refreshed = find_user(session, tenant_id, user_id)
        if refreshed is None:
            raise NotFound(f"user {user_id} not found in tenant {tenant_id}")
        raise Conflict(
            f"concurrent modification on user {user_id}: expected version {expected_version}, "
            f"current {refreshed['version']}"
        )
    return row
