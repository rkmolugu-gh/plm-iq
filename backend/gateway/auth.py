"""Login sessions and identity resolution for the gateway.

A successful sign-in stores a signed cookie carrying the tenant and user
ids; every later request re-loads tenant, user, roles, and edition from
the database (services layer, no dummy data), so revoked or edited
accounts take effect immediately. The signed cookie is tamper-proof but
unencrypted: it holds ids only, never credentials.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from itsdangerous import BadSignature, URLSafeSerializer

from .settings import edition_label

logger = logging.getLogger(__name__)

_COOKIE_NAME = "plmiq_session"
_MAX_AGE_SECONDS = 12 * 60 * 60  # half a work day; sign-in again after that
_REMEMBER_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # 'Keep me signed in': 30 days


def _serializer() -> URLSafeSerializer:
    # built lazily: itsdangerous takes the secret at construction time and
    # the .env SECRET_KEY must win over any hardcoded fallback
    import os

    return URLSafeSerializer(os.getenv("SECRET_KEY", "arandomstring"), salt="plmiq-session")


def encode_session(tenant_id: str, user_id: str) -> str:
    return _serializer().dumps({"t": tenant_id, "u": user_id})


def decode_session(token: str | None) -> tuple[str, str] | None:
    if not token:
        return None
    try:
        payload = _serializer().loads(token)
        return str(payload["t"]), str(payload["u"])
    except (BadSignature, KeyError, TypeError):
        return None


@dataclass(frozen=True)
class Identity:
    """Everything the UI needs about who is signed in right now."""

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


def load_identity(session_cookie: str | None) -> Identity | None:
    """Resolve the signed session cookie against live database rows.

    Returns None when absent/invalid/expired or when either row has since
    been removed or disabled - the request is then treated as anonymous.
    """
    ids = decode_session(session_cookie)
    if ids is None:
        return None
    tenant_id, user_id = ids

    from uuid import UUID

    from services import db, role_service, tenant_service, user_service

    try:
        tid, uid = UUID(tenant_id), UUID(user_id)
        with db.admin_session() as session:
            tenant = tenant_service.get_tenant(session, tid)
            if tenant["status"] in ("archived",):
                return None
        with db.tenant_session(tid) as session:
            user = user_service.get_user(session, tid, uid)
            if user["status"] != "active":
                return None
            roles = role_service.list_user_roles(session, tid, uid)
    except Exception:
        logger.warning("auth.identity.unresolvable", extra={"tenant": tenant_id, "user": user_id})
        return None

    role_names = [r.name for r in roles]
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


def _uuid(value) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def authenticate(subdomain: str, login_id: str, password: str) -> tuple[str, str] | None:
    """Verify tenant + login id + password; returns (tenant_id, user_id).

    Runs entirely through the services layer: the tenant must exist and be
    active, the account must belong to it and be active, and the stored
    bcrypt hash must match. Accounts without a password hash cannot sign in.
    """
    import bcrypt
    from services import db, tenant_service, user_service

    try:
        with db.admin_session() as session:
            tenant = tenant_service.find_tenant_by_subdomain(session, subdomain.strip().lower())
        if tenant is None or tenant["status"] != "active":
            return None
        with db.admin_session() as session:
            user = user_service.find_user_by_login(session, login_id)
        if user is None or _uuid(user["tenant_id"]) != _uuid(tenant["id"]):
            return None
        if user["status"] != "active" or not user.get("password_hash"):
            return None
        if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return None
        tid = _uuid(user["tenant_id"])
        with db.tenant_session(tid) as session:
            user_service.record_login(session, tid, user["id"], actor=user["email"])
        return str(tid), str(user["id"])
    except Exception:
        logger.exception("auth.authenticate.failed")
        return None
