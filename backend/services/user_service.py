"""UserService - tenant-scoped user account management for iam_user.

Why this class exists
---------------------
Every operation runs inside ``tenant_session(tenant_id)``; row-level security
plus explicit tenant_id predicates keep accounts isolated per workspace.
Email is the globally unique login identifier (lower(email) index in 002) and
accepts either an email address or a bare login id such as 'plm-iq'.

This class previously duplicated ``_execute_versioned_update`` and
``_check_transition`` from the vertex side - the duplication that triggered
the BaseService extraction. Both now come from BaseService.

Benefits
--------
* One optimistic-lock implementation across vertex/user/edge/... services.
* Login-sensitive operations (find_by_login, record_login) document their
  admin-session/RLS contracts right on the methods that need them.

How to extend (future scenarios)
--------------------------------
* MFA enrollment, API tokens, avatar -> new columns + methods here.
* Cross-workspace identity merge -> extend assign_to_tenant's contract.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime as dt
from uuid import UUID

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import enums, tables
from .base import BaseService
from .errors import Conflict, NotFound, ValidationFailed
from .schemas import Page, UserCreate, UserOut, UserUpdate

logger = logging.getLogger(__name__)

# Bare login ids (no '@') mirror the ck_user_email check in 002.
LOGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

_USER_TRANSITIONS = {
    enums.UserStatus.ACTIVE: frozenset({enums.UserStatus.DISABLED, enums.UserStatus.LOCKED}),
    enums.UserStatus.DISABLED: frozenset({enums.UserStatus.ACTIVE}),
    enums.UserStatus.LOCKED: frozenset({enums.UserStatus.ACTIVE, enums.UserStatus.DISABLED}),
}

_UPDATABLE_FIELDS = frozenset(
    {"full_name", "is_tenant_admin", "password_hash", "mfa_enabled", "status"}
)

_MAX_LIMIT = 200


class UserService(BaseService):
    out_model = UserOut
    transitions = _USER_TRANSITIONS

    def _to_out(self, row):
        """DTO mapper that drops the sensitive ``password_hash`` column."""
        mapping = dict(getattr(row, "_mapping", row))
        mapping.pop("password_hash", None)
        return UserOut.model_validate(mapping)

    # ── reads ────────────────────────────────────────────────────────────────

    def find_by_login(self, session: Session, login_id: str) -> dict | None:
        """Resolve a globally unique login id (email or bare id) to a user.

        Login happens before any tenant is known, so callers must run this via
        ``db.admin_session()`` - iam_user's RLS policy would otherwise deny
        every row. Verify ``password_hash`` with bcrypt before trusting it.
        """
        row = session.execute(
            select(tables.iam_user).where(func.lower(tables.iam_user.c.email) == login_id.strip().lower())
        ).one_or_none()
        return dict(row._mapping) if row else None

    def find(self, session: Session, tenant_id: UUID, user_id: UUID) -> dict | None:
        return self._fetch_one(session, tables.iam_user, row_id=user_id, tenant_id=tenant_id)

    def get(self, session: Session, tenant_id: UUID, user_id: UUID) -> dict:
        user = self.find(session, tenant_id, user_id)
        if user is None:
            raise NotFound(f"user {user_id} not found in tenant {tenant_id}")
        return user

    def list(
        self,
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
        return Page[UserOut](items=[self._to_out(r) for r in rows],
                             total=total, limit=limit, offset=offset)

    def list_outside_tenant(self, session: Session, tenant_id: UUID, *, limit: int = 200) -> list[UserOut]:
        """Accounts NOT in the given tenant - candidates for 'add existing user'.

        Cross-tenant read: run via ``db.admin_session()``.
        """
        rows = session.execute(
            select(tables.iam_user)
            .where(tables.iam_user.c.tenant_id != tenant_id)
            .order_by(tables.iam_user.c.email)
            .limit(min(max(limit, 1), _MAX_LIMIT))
        ).all()
        return [self._to_out(r) for r in rows]

    # ── writes ───────────────────────────────────────────────────────────────

    def create(self, session: Session, tenant_id: UUID, data: UserCreate, actor: str) -> UserOut:
        if "@" not in data.email and not LOGIN_ID_RE.fullmatch(data.email):
            raise ValidationFailed(
                f"invalid login id '{data.email}': must be an email address or match {LOGIN_ID_RE.pattern}"
            )
        values = data.model_dump(exclude_unset=True, exclude={"role"})
        values.update(tenant_id=tenant_id, created_by=actor, modified_by=actor)
        try:
            row = session.execute(
                insert(tables.iam_user).values(**values).returning(*tables.iam_user.c)
            ).one()
        except IntegrityError as exc:
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
            logger.warning("user.create.integrity", extra={"tenant": str(tenant_id), "constraint": constraint})
            if "tenant" in constraint:
                raise Conflict(f"tenant {tenant_id} does not exist") from exc
            raise Conflict(f"a user with email '{data.email}' already exists") from exc
        role_code = (data.role or "").strip()
        if role_code:
            self._assign_role_at_creation(session, tenant_id, row.id, role_code, actor=actor)
        logger.info("user.created", extra={
            "tenant": str(tenant_id), "user": str(row.id), "actor": actor,
        })
        return self._to_out(row)

    def update(
        self, session: Session, tenant_id: UUID, user_id: UUID, data: UserUpdate, actor: str
    ) -> UserOut:
        current = self.get(session, tenant_id, user_id)
        if current["version"] != data.version:
            raise Conflict(
                f"version mismatch on user {user_id}: expected {data.version}, "
                f"current {current['version']}"
            )
        changes = data.model_dump(exclude_unset=True, exclude={"version"})
        unknown = set(changes) - _UPDATABLE_FIELDS
        if unknown:
            raise ValidationFailed(f"fields not updatable on a user: {sorted(unknown)}")
        if "status" in changes:
            self._check_transition(row_id=user_id, old=current["status"], new=changes["status"])
        if not changes:
            return self._to_out(dict(current))
        updated = self._versioned_update(
            session,
            tables.iam_user,
            changes,
            row_id=user_id,
            tenant_id=tenant_id,
            expected_version=data.version,
            actor=actor,
        )
        logger.info("user.updated", extra={
            "tenant": str(tenant_id), "user": str(user_id), "actor": actor,
        })
        return self._to_out(updated)

    def assign_to_tenant(self, session: Session, target_tenant_id: UUID, login_id: str, actor: str) -> UserOut:
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
        logger.info("user.tenant_assigned", extra={
            "tenant": str(target_tenant_id), "user": str(row.id), "actor": actor,
        })
        return self._to_out(updated)

    def record_login(self, session: Session, tenant_id: UUID, user_id: UUID, *, actor: str | None = None) -> UserOut:
        """Stamp last_login_on after a successful authentication.

        Deliberately skips the version guard: the login flow has no prior read
        to race against and must never fail because an admin edited the profile.
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
        return self._to_out(row)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _assign_role_at_creation(
        self, session: Session, tenant_id: UUID, user_id: UUID, code: str, *, actor: str
    ) -> dict:
        """Attach a visible role (global or own-tenant) to a freshly created user."""
        row = session.execute(
            select(tables.iam_role).where(
                tables.iam_role.c.code == code,
                or_(
                    tables.iam_role.c.scope == enums.RoleScope.GLOBAL,
                    tables.iam_role.c.tenant_id == tenant_id,
                ),
            )
        ).one_or_none()
        if row is None:
            raise ValidationFailed(f"unknown role '{code}' for this tenant")
        session.execute(
            insert(tables.iam_user_role).values(
                user_id=user_id, role_id=row.id, tenant_id=tenant_id, assigned_by=actor
            )
        )
        logger.info("user.role_assigned", extra={
            "tenant": str(tenant_id), "user": str(user_id), "role": code, "actor": actor,
        })
        return dict(row._mapping)


#: Shared singleton for the gateway and sibling services.
users = UserService()
