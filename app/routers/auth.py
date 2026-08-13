"""Authentication router — login, logout, and session management."""

import logging
from typing import List, Optional

import bcrypt
from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import SMTP_ENABLED
from app.database import get_db, TenantScopedSession
from app.models import User, Tenant
from app.template_utils import render


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()

logger = logging.getLogger(__name__)

router = APIRouter()


def get_tenant_key(request: Request, db: Optional[Session] = None) -> Optional[str]:
    """Return the tenant_key for the current request.

    Resolution order:
    1. Subdomain (from request.state, set by the tenant middleware)
    2. Logged-in user's tenant_key (when on the apex domain / no subdomain)

    Returns None only when neither a subdomain nor a logged-in user resolves —
    callers must treat None as deny (never query unscoped).
    """
    tenant_key = getattr(request.state, "tenant_key", None)
    if tenant_key is None and db is not None:
        user_id = request.session.get("user_id")
        if user_id is not None:
            user = db.query(User).filter(User.user_id == user_id).first()
            if user and user.tenant_key:
                tenant_key = user.tenant_key
    return tenant_key


def get_tenant_db(request: Request, db: Session = Depends(get_db)) -> TenantScopedSession:
    """FastAPI dependency that returns a tenant-scoped database session.

    All queries on models with a ``tenant_key`` column are automatically
    filtered to the current tenant.  Models without ``tenant_key``
    (e.g. Role, AppSetting) are returned unscoped.

    Resolution order:
    1. Subdomain (from request state, set by middleware)
    2. Logged-in user's tenant_key (when on apex domain)
    """
    tenant_key = get_tenant_key(request, db)
    return TenantScopedSession(db, tenant_key)


def get_current_user(request: Request, db: TenantScopedSession = Depends(get_tenant_db)) -> Optional[User]:
    """Fetch the logged-in User from session, scoped to the resolved tenant.

    If the request arrived on a tenant subdomain, a session user whose
    tenant_key does not match that tenant is treated as unauthenticated —
    this prevents a cookie from one subdomain being honored on another.
    """
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user or not user.is_active:
        return None
    tenant = getattr(request.state, "tenant", None)
    if tenant is not None and user.tenant_id != tenant.tenant_id:
        return None
    return user


def require_user(request: Request, db: TenantScopedSession = Depends(get_tenant_db)) -> User:
    """Like get_current_user but redirects to login if unauthenticated."""
    user = get_current_user(request, db)
    if user is None:
        raise _RedirectToLogin(f"/login?next={request.url.path}")
    return user


def is_superuser(user: Optional[User]) -> bool:
    """A superuser is the global masteradmin, identified by a NULL role or
    the 'superadmin' role.

    Only the masteradmin may add tenants, manage global roles, create workflow
    templates, and create queries/reports. `tenantadmin` is a per-tenant admin
    (scoped) and is handled separately.
    """
    return user is not None and (user.role is None or user.role == "superadmin")


def require_superuser(request: Request, db: TenantScopedSession = Depends(get_tenant_db)) -> User:
    """Dependency that only allows the global masteradmin/superadmin."""
    user = require_user(request, db)
    if not is_superuser(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the masteradmin may perform this action.",
        )
    return user


def require_role(allowed_roles: List[str]):
    """Dependency that ensures the current user has one of the allowed roles.

    A NULL-role superuser (masteradmin), the `superadmin` role, and the
    `tenantadmin` role all satisfy any role list: the masteradmin/superadmin
    is global, and `tenantadmin` is the per-tenant admin with full management
    rights within its tenant.
    """
    def role_checker(request: Request, db: TenantScopedSession = Depends(get_tenant_db)) -> User:
        user = require_user(request, db)
        if is_superuser(user) or user.role == "tenantadmin" or user.role in allowed_roles:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
    return role_checker


class _RedirectToLogin(Exception):
    """Raised by require_user — caught by middleware in main.py to redirect to login."""
    def __init__(self, location: str):
        self.location = location


def resolve_tenant(request: Request, db: Session) -> Optional["Tenant"]:
    """Map the request's subdomain to a Tenant, or None.

    `tenant1.plm-iq.com` → tenant with `subdomain='tenant1'`.
    The bare apex host (e.g. `localhost`, `plm-iq.com`) resolves to None
    so single-tenant / local-dev usage still works.
    """
    from app.config import BASE_DOMAIN

    host = (request.url.hostname or "").lower()
    if not host or host == BASE_DOMAIN:
        return None
    # Strip the base domain to recover the leftmost subdomain label.
    if host.endswith("." + BASE_DOMAIN):
        label = host[: -(len(BASE_DOMAIN) + 1)]
    elif "." in host:
        # e.g. "tenant.localhost" — base domain is "localhost", so the
        # first label is the subdomain.
        label = host.split(".")[0]
    else:
        return None
    if not label or label == host:
        return None
    return db.query(Tenant).filter(Tenant.subdomain == label).first()


def _hash_password(password: str) -> str:
    """Hash a password with bcrypt (returns a utf-8 string)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Template context helper: inject current_user and current_tenant into
# every render() call.  All routers should use this.
# ---------------------------------------------------------------------------

def resolve_tenant_key(tenant) -> Optional[str]:
    """Return the tenant_key for a Tenant object (or None)."""
    return tenant.tenant_key if tenant is not None else None


def get_settings(request: Request) -> "TenantSettings":
    """Return the TenantSettings resolved for this request.

    Populated by auth_context() (see below) onto request.state. Never raises:
    falls back to global defaults when not yet resolved.
    """
    from app.settings import TenantSettings

    settings = getattr(request.state, "settings", None)
    if settings is None:
        return TenantSettings({})
    return settings


def auth_context(request: Request, db: TenantScopedSession) -> dict:
    """Return dict with current_user, current_tenant and settings for templates.

    The tenant_key is also stored on request.state by the tenant resolution
    middleware so that all routes (including API routes) can access it.

    ``TenantSettings`` (the centralised domain option lists) is loaded here for
    the resolved tenant, stored on ``request.state.settings`` for backend
    modules, and included in the template context as ``settings`` and as the
    individual constant lists (``statuses``, ``change_types``, etc.) so
    templates keep using the same names.
    """
    from app.settings import load_tenant_settings

    user = get_current_user(request, db)
    tenant = getattr(request.state, "tenant", None)
    # Fall back to a DB lookup by user.tenant_id when request.state.tenant
    # is not set (e.g. apex-host / single-tenant local dev usage).
    if tenant is None and user is not None:
        tenant = db.query(Tenant).filter(Tenant.tenant_id == user.tenant_id).first()

    tenant_key = resolve_tenant_key(tenant)
    settings = load_tenant_settings(db, tenant_key)
    request.state.settings = settings

    inbox_count = 0
    unread_count = 0
    all_users = None
    user_map = {}
    if user:
        from app.notifications import inbox_counts
        inbox_count, unread_count = inbox_counts(db, user)
        all_users = db.query(User).order_by(User.username).all()
        user_map = {u.user_id: u.full_name for u in all_users}

    ctx = {
        "current_user": user,
        "current_tenant": tenant,
        "tenant_key": tenant_key,
        "tenant_secret": tenant.tenant_secret if tenant else None,
        "inbox_count": inbox_count,
        "unread_count": unread_count,
        "all_users": all_users,
        "user_map": user_map,
        "settings": settings,
    }
    return ctx


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_form(request: Request, error: str = "", db: TenantScopedSession = Depends(get_tenant_db)):
    """Render the login form with the seed-user quick-login selector."""
    all_users = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.username)
        .all()
    )
    return HTMLResponse(content=render(
        "login.html",
        request=request,
        error=error,
        all_users=all_users,
    ))


@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
def login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/"),
    email: str = Form(""),
    username: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Authenticate user and create session.

    The login identifier is the user's EMAIL (the logical user id). For
    backwards compatibility with the seed quick-login (which submits
    usernames), a username is also accepted as a fallback.
    """
    identifier = (email or username or "").strip()
    user = db.query(User).filter(
        (User.email == identifier) | (User.username == identifier)
    ).first()

    if not user or not user.is_active:
        return _login_error(request, db, "Invalid email or password.")

    if not user.email_verified:
        return _login_error(request, db,
                            "Your email is not verified yet. Please check your inbox "
                            "for the verification link.")

    if not _check_password(password, user.password_hash or ""):
        return _login_error(request, db, "Invalid email or password.")

    # Set session
    request.session["user_id"] = user.user_id
    logger.info(f"User '{user.username}' (id={user.user_id}) logged in")

    return RedirectResponse(url=next, status_code=303)


def _login_error(request: Request, db, message: str) -> HTMLResponse:
    all_users = db.query(User).filter(User.is_active.is_(True)).order_by(User.username).all()
    return HTMLResponse(content=render(
        "login.html",
        request=request,
        error=message,
        all_users=all_users,
    ))


@router.post("/logout", response_class=HTMLResponse, include_in_schema=False)
def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.post("/switch-user", include_in_schema=False)
def switch_user(
    request: Request,
    user_id: int = Form(...),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Development helper: switch to a different user without logging out."""
    current_user = require_user(request, db)
    target = db.query(User).filter(User.user_id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    request.session["user_id"] = target.user_id
    logger.info("User '%s' switched session to user '%s'", current_user.username, target.username)
    back = request.headers.get("Referer", "/")
    return RedirectResponse(url=back, status_code=303)


# ---------------------------------------------------------------------------
# Self-service registration + email verification + password reset
# ---------------------------------------------------------------------------

def _make_tenant_key(name: str) -> str:
    """Propose a unique-ish tenant_key from the tenant name."""
    import re as _re
    base = _re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"tk_{base or 'tenant'}"


def _email_in_use(db, email: str) -> bool:
    return db.query(User).filter(User.email == email).first() is not None


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_form(request: Request, error: str = ""):
    """Render the new-tenant registration form."""
    return HTMLResponse(content=render(
        "auth/register.html",
        request=request,
        error=error,
    ))


@router.post("/register", response_class=HTMLResponse, include_in_schema=False)
def register_submit(
    request: Request,
    tenant_name: str = Form(...),
    admin_name: str = Form(...),
    admin_email: str = Form(...),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Create a new tenant + unverified tenant-admin, then email a verify link."""
    tenant_name = (tenant_name or "").strip()
    admin_name = (admin_name or "").strip()
    admin_email = (admin_email or "").strip().lower()

    if not tenant_name or not admin_name or not admin_email:
        return _render_register(request, error="All fields are required.")
    if db.query(Tenant).filter(Tenant.tenant_name == tenant_name).first():
        return _render_register(request, error=f"Tenant '{tenant_name}' already exists.")
    if _email_in_use(db, admin_email):
        return _render_register(request, error="An account with that email already exists.")

    # Tenant
    tenant_key = _make_tenant_key(tenant_name)
    from app.routers.admin import _provision_tenant_git
    tenant = Tenant(
        tenant_name=tenant_name,
        tenant_key=tenant_key,
        tenant_secret="",
        role="reader",
        is_active=True,
        created_date=_today(),
    )
    db.add(tenant)
    db.flush()

    # Tenant-admin (email is the login id), unverified, no password yet.
    user = User(
        username=admin_email.split("@")[0],
        full_name=admin_name,
        email=admin_email,
        email_verified=False,
        password_hash="",
        tenant_id=tenant.tenant_id,
        tenant_key=tenant_key,
        role="tenantadmin",
        is_active=True,
        created_date=_today(),
    )
    db.add(user)
    db.commit()
    try:
        _provision_tenant_git(tenant)
    except Exception:  # noqa: BLE001 - best-effort; lazy retry later
        pass

    from app.email_verify import send_verification_email
    link = send_verification_email(request, user, "register")

    return HTMLResponse(content=render(
        "auth/confirm_register.html",
        request=request,
        email=admin_email,
        dev_link=link,
        smtp_enabled=SMTP_ENABLED,
    ))


def _render_register(request: Request, error: str) -> HTMLResponse:
    return HTMLResponse(content=render(
        "auth/register.html", request=request, error=error,
    ))


@router.get("/verify/{token}", response_class=HTMLResponse, include_in_schema=False)
def verify_form(request: Request, token: str, error: str = ""):
    """Render the set-password form for a valid token."""
    from app.email_verify import read_token
    data = read_token(token)
    if data is None:
        return HTMLResponse(content=render(
            "auth/verify.html", request=request,
            invalid=True, error="This link is invalid or has expired (valid 1 hour).",
        ))
    uid, email = data
    return HTMLResponse(content=render(
        "auth/verify.html", request=request,
        token=token, uid=uid, email=email, invalid=False, error=error,
    ))


@router.post("/verify/{token}", response_class=HTMLResponse, include_in_schema=False)
def verify_submit(
    request: Request,
    token: str,
    password: str = Form(...),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Set the user's password, mark email verified, and log them in."""
    from app.email_verify import read_token
    data = read_token(token)
    if data is None:
        return HTMLResponse(content=render(
            "auth/verify.html", request=request,
            invalid=True, error="This link is invalid or has expired (valid 1 hour).",
        ))
    uid, email = data
    if not password or len(password) < 6:
        return verify_form(request, token, error="Password must be at least 6 characters.")

    user = db.query(User).filter(User.user_id == uid, User.email == email).first()
    if not user:
        return HTMLResponse(content=render(
            "auth/verify.html", request=request,
            invalid=True, error="Account not found.",
        ))
    user.password_hash = _hash_password(password)
    user.email_verified = True
    db.commit()

    request.session["user_id"] = user.user_id
    return RedirectResponse(url="/", status_code=303)


@router.get("/forgot", response_class=HTMLResponse, include_in_schema=False)
def forgot_form(request: Request, error: str = "", sent: bool = False):
    """Render the forgot-password form."""
    return HTMLResponse(content=render(
        "auth/forgot.html", request=request, error=error, sent=sent,
    ))


@router.post("/forgot", response_class=HTMLResponse, include_in_schema=False)
def forgot_submit(
    request: Request,
    email: str = Form(...),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Send a reset link for an existing email (no user enumeration)."""
    email = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        from app.email_verify import send_verification_email
        send_verification_email(request, user, "reset")
        logger.info("Password reset link sent to %s", email)
    # Always render the same confirmation regardless of whether the email exists.
    return forgot_form(request, sent=True)