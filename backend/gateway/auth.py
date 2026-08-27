"""SessionManager - login sessions and identity resolution for the gateway.

A successful sign-in stores a signed cookie carrying the tenant and user
ids; every later request re-loads tenant, user, roles, and edition from the
database (services layer, no dummy data), so revoked or edited accounts take
effect immediately. The signed cookie is tamper-proof but unencrypted: it
holds ids only, never credentials.

Why a class
-----------
Cookie signing (secret, salt) and identity resolution (three DB lookups)
belong to one collaborator the gateway injects - not to loose functions over
module state. Tests build a SessionManager with a throwaway secret and stub
services.

How to extend (future scenarios)
--------------------------------
* OIDC/SAML SSO (Business tier roadmap) -> add ``exchange_external_token``
  here returning the same (tenant_id, user_id) pair; cookies unchanged.
* Refresh tokens / sliding expiry -> subclass and override cookie max-age.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.exc import OperationalError

from .settings import edition_label


class DatabaseUnavailable(Exception):
    """Raised when authentication cannot reach the database (e.g. it is down)."""

logger = logging.getLogger(__name__)

_COOKIE_NAME = "plmiq_session"
_MAX_AGE_SECONDS = 12 * 60 * 60  # half a work day; sign-in again after that
_REMEMBER_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 'Keep me signed in': 30 days


@dataclass
class Identity:
    """Everything the UI needs about who is signed in right now.

    ``session`` is populated by the gateway during request resolution: it is the
    request-scoped tenant RLS session the assistant (and any tool) should reuse
    instead of opening its own. It is ``None`` until the auth flow attaches it.
    """

    tenant_id: str
    tenant_name: str
    subdomain: str
    edition_id: str
    edition_label_: str
    tenant_status: str
    user_id: str
    email: str
    full_name: str
    is_tenant_admin: bool
    role_names: list[str]
    role_label: str
    session: Any = None


class SessionManager:
    def __init__(self, secret: str):
        self._secret = secret

    def _serializer(self) -> URLSafeSerializer:
        return URLSafeSerializer(self._secret, salt="plmiq-session")

    # ── cookie codec ─────────────────────────────────────────────────────────

    def encode_session(self, tenant_id: str, user_id: str) -> str:
        return self._serializer().dumps({"t": tenant_id, "u": user_id})

    def decode_session(self, token: str | None) -> tuple[str, str] | None:
        if not token:
            return None
        try:
            payload = self._serializer().loads(token)
            return str(payload["t"]), str(payload["u"])
        except (BadSignature, KeyError, TypeError):
            return None

    @property
    def cookie_name(self) -> str:
        return _COOKIE_NAME

    @property
    def max_age_seconds(self) -> int:
        return _MAX_AGE_SECONDS

    @property
    def remember_max_age_seconds(self) -> int:
        return _REMEMBER_MAX_AGE_SECONDS

    # ── identity resolution ──────────────────────────────────────────────────

    def load_identity(self, session_cookie: str | None) -> Identity | None:
        """Resolve the signed session cookie against live database rows.

        Returns None when absent/invalid/expired or when either row has since
        been removed or disabled - the request is then treated as anonymous.
        """
        ids = self.decode_session(session_cookie)
        if ids is None:
            return None
        tenant_id, user_id = ids

        from services import db
        from services.role_service import roles
        from services.tenant_service import tenants
        from services.user_service import users

        try:
            tid, uid = UUID(tenant_id), UUID(user_id)
            with db.admin_session() as session:
                tenant = tenants.get(session, tid)
                if tenant["status"] in ("archived",):
                    return None
            with db.tenant_session(tid) as session:
                user = users.get(session, tid, uid)
                if user["status"] != "active":
                    return None
                roles_list = roles.list_user_roles(session, tid, uid)
        except Exception:
            logger.warning("auth.identity.unresolvable", extra={
                "tenant": tenant_id, "user": user_id,
            })
            return None

        role_names = [r.name for r in roles_list]
        label = ", ".join(role_names) if role_names else (
            "Tenant Administrator" if user["is_tenant_admin"] else "User"
        )
        # DB rows hand back enum members; keep the canonical value string
        # ('foundation') instead of str() noise like 'EditionId.FOUNDATION'.
        raw_edition = tenant["edition_id"]
        edition_id = getattr(raw_edition, "value", raw_edition)
        return Identity(
            tenant_id=tenant_id,
            tenant_name=tenant["name"],
            subdomain=tenant["subdomain"],
            edition_id=edition_id,
            edition_label_=edition_label(edition_id),
            tenant_status=tenant["status"],
            user_id=user_id,
            email=user["email"],
            full_name=user["full_name"],
            is_tenant_admin=bool(user["is_tenant_admin"]),
            role_names=role_names,
            role_label=label,
        )

    def authenticate(self, subdomain: str, login_id: str, password: str) -> tuple[str, str] | None:
        """Verify tenant + login id + password; returns (tenant_id, user_id).

        Runs entirely through the services layer: the tenant must exist and be
        active, the account must belong to it and be active, and the stored
        bcrypt hash must match. Accounts without a password hash cannot sign in.
        """
        import bcrypt

        from services import db
        from services.tenant_service import tenants
        from services.user_service import users

        try:
            with db.admin_session() as session:
                tenant = tenants.find_by_subdomain(session, subdomain.strip().lower())
            if tenant is None or tenant["status"] != "active":
                return None
            with db.admin_session() as session:
                user = users.find_by_login(session, login_id)
            if user is None or UUID(str(user["tenant_id"])) != UUID(str(tenant["id"])):
                return None
            if user["status"] != "active" or not user.get("password_hash"):
                return None
            if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                return None
            tid = UUID(str(user["tenant_id"]))
            with db.tenant_session(tid) as session:
                users.record_login(session, tid, user["id"], actor=user["email"])
            return str(tid), str(user["id"])
        except OperationalError:
            # Database is unreachable (down, not accepting connections). Surface a
            # distinct, user-friendly signal instead of a generic "invalid" error.
            logger.exception("auth.authenticate.db_unavailable")
            raise DatabaseUnavailable("The database is currently unavailable.") from None
        except Exception:
            logger.exception("auth.authenticate.failed")
            return None


#: Shared singleton; secret arrives via .env (SECRET_KEY), same as before.
import os as _os

sessions = SessionManager(_os.getenv("SECRET_KEY", "arandomstring"))
