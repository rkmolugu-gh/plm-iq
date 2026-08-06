"""Authentication router — login, logout, and session management."""

import logging
from typing import List, Optional

import bcrypt
from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Tenant
from app.template_utils import render

logger = logging.getLogger(__name__)

router = APIRouter()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Fetch the logged-in User from session, scoped to the resolved tenant.

    If the request arrived on a tenant subdomain, a session user whose
    tenant_id does not match that tenant is treated as unauthenticated —
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


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
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


def require_superuser(request: Request, db: Session = Depends(get_db)) -> User:
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
    def role_checker(request: Request, db: Session = Depends(get_db)) -> User:
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

def auth_context(request: Request, db: Session) -> dict:
    """Return dict with current_user and current_tenant for template context.

    The tenant_key is also stored on request.state by the tenant resolution
    middleware so that all routes (including API routes) can access it.
    """
    user = get_current_user(request, db)
    tenant = getattr(request.state, "tenant", None)
    # Fall back to a DB lookup by user.tenant_id when request.state.tenant
    # is not set (e.g. apex-host / single-tenant local dev usage).
    if tenant is None and user is not None:
        tenant = db.query(Tenant).filter(Tenant.tenant_id == user.tenant_id).first()
    inbox_count = 0
    unread_count = 0
    all_users = None
    if user:
        from app.notifications import inbox_counts
        inbox_count, unread_count = inbox_counts(db, user)
        all_users = db.query(User).order_by(User.username).all()
    return {
        "current_user": user,
        "current_tenant": tenant,
        "tenant_key": tenant.tenant_key if tenant else None,
        "inbox_count": inbox_count,
        "unread_count": unread_count,
        "all_users": all_users,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_form(request: Request, error: str = "", db: Session = Depends(get_db)):
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
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    """Authenticate user and create session."""
    # Look up user by username
    user = db.query(User).filter(User.username == username).first()

    if not user or not user.is_active:
        all_users = db.query(User).filter(User.is_active.is_(True)).order_by(User.username).all()
        return HTMLResponse(content=render(
            "login.html",
            request=request,
            error="Invalid username or password.",
            all_users=all_users,
        ))

    if not _check_password(password, user.password_hash or ""):
        all_users = db.query(User).filter(User.is_active.is_(True)).order_by(User.username).all()
        return HTMLResponse(content=render(
            "login.html",
            request=request,
            error="Invalid username or password.",
            all_users=all_users,
        ))

    # Set session
    request.session["user_id"] = user.user_id
    logger.info(f"User '{user.username}' (id={user.user_id}) logged in")

    return RedirectResponse(url=next, status_code=303)


@router.post("/logout", response_class=HTMLResponse, include_in_schema=False)
def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.post("/role", include_in_schema=False)
def change_role(
    request: Request,
    role: str = Form(...),
    db: Session = Depends(get_db),
):
    """Let the signed-in user switch their own role between 'reader' and 'author'."""
    user = require_user(request, db)
    back = request.headers.get("Referer", "/")
    if role not in ("reader", "author"):
        return RedirectResponse(url=back, status_code=303)
    if user.role != role:
        user.role = role
        db.commit()
        logger.info("User '%s' changed own role to '%s'", user.username, role)
    return RedirectResponse(url=back, status_code=303)


@router.post("/switch-user", include_in_schema=False)
def switch_user(
    request: Request,
    user_id: int = Form(...),
    db: Session = Depends(get_db),
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