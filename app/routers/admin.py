"""Admin router — user & tenant management (tree UI).

Tenants are tree nodes; users are their children. All routes require the
`admin` role. Tenants must be empty (no users, no parts) before they can be
deleted — deletion never cascades automatically.
"""

import datetime
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.database import TenantScopedSession
from app.models import Tenant, User, Part, AppSetting
from app.models.role import role_names, role_rows
from app.routers.auth import require_user, require_role, require_superuser, auth_context, is_superuser, _hash_password, get_tenant_db
from app.settings import GLOBAL_TENANT_KEY, invalidate_tenant_settings
from app.template_utils import render
from app.config import BASE_DOMAIN

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")


def _today() -> str:
    return datetime.date.today().isoformat()


def _valid_role(db: Session, role: str) -> str:
    """Return `role` if it exists in the catalog, else the default 'reader'."""
    return role if role in set(role_names(db)) else "reader"


def _provision_tenant_git(tenant) -> bool:
    """Provision the tenant's isolated Gitea identity + private repos.

    Returns True on success. Never raises: failures are logged and surface as a
    non-provisioned tenant so lazy provisioning can retry on first use.
    """
    try:
        from app.git.tenant_gitea import provision_tenant_gitea
        ok = provision_tenant_gitea(tenant)
    except Exception as e:
        logger.warning("TENANT_GIT_PROVISION failed tenant=%s: %s",
                       getattr(tenant, "tenant_key", "?"), e)
        return False
    if not ok:
        logger.warning("TENANT_GIT_PROVISION returned failure tenant=%s "
                       "(Gitea may be down; will lazy-provision on first use)",
                       getattr(tenant, "tenant_key", "?"))
    return ok


def _tenant_admins(db: Session, tenant_id: int, active_only: bool = True):
    """Return the users who are `tenantadmin` for a tenant."""
    q = db.query(User).filter(User.tenant_id == tenant_id, User.role == "tenantadmin")
    if active_only:
        q = q.filter(User.is_active == True)  # noqa: E712
    return q.all()


def _enforce_one_admin_per_tenant(
    db: Session, tenant_id: int, editing_user_id: Optional[int] = None,
    new_role: Optional[str] = None,
) -> Optional[str]:
    """Guard the "exactly one tenantadmin per tenant" rule.

    Returns an error string if the requested change would break the rule, else None.

    - Assigning `tenantadmin` when the tenant already has a different tenantadmin → blocked.
    - Removing (delete or role-change away from `tenantadmin`) the tenant's only
      tenantadmin → blocked.
    """
    admins = _tenant_admins(db, tenant_id, active_only=False)
    admin_ids = {u.user_id for u in admins}
    if new_role == "tenantadmin":
        others = admin_ids - ({editing_user_id} if editing_user_id else set())
        if others:
            return "This tenant already has an admin (tenantadmin). Only one is allowed per tenant."
    else:
        # A change that removes tenantadmin from `editing_user_id` (delete or role change).
        if editing_user_id in admin_ids and len(admin_ids) <= 1:
            return "Cannot remove the only admin (tenantadmin) of this tenant. Assign another admin first."
    return None


def _render_tree(request: Request, db: Session, error: Optional[str] = None,
                 selected_tenant: Optional[Tenant] = None,
                 selected_user: Optional[User] = None) -> HTMLResponse:
    """Render the management tree with optional selection and error message.

    Scope: the masteradmin (NULL role) sees all tenants; a `tenantadmin` sees only
    their own tenant. Tenant/role management controls are masteradmin-only.
    """
    ctx = auth_context(request, db)
    current = ctx.get("current_user")
    superuser = is_superuser(current)
    if superuser:
        tenants = db.query(Tenant).order_by(Tenant.tenant_name).all()
    else:
        tenants = db.query(Tenant).filter(
            Tenant.tenant_id == (current.tenant_id if current else -1)
        ).all()
    return HTMLResponse(content=render(
        "admin/list.html",
        **ctx,
        tenants=tenants,
        error=error,
        selected_tenant=selected_tenant,
        selected_user=selected_user,
        selected_tenant_id=selected_tenant.tenant_id if selected_tenant else None,
        selected_user_id=selected_user.user_id if selected_user else None,
        user_roles=role_names(db),
        tenant_roles=role_names(db),
        roles=role_rows(db),
        base_domain=BASE_DOMAIN,
        can_manage_tenants=superuser,
        can_manage_roles=superuser,
        user_tenant_locked=not superuser,
        show_inactive_users=_get_setting(db, "showinactiveusers", "true").lower() != "false",
    ))


def _load_tenant(db: Session, tid: int) -> Optional[Tenant]:
    return db.query(Tenant).filter(Tenant.tenant_id == tid).first()


def _load_user(db: Session, uid: int) -> Optional[User]:
    return db.query(User).filter(User.user_id == uid).first()


def _get_setting(db: Session, key: str, default: str = "") -> str:
    """Return the value of an app setting, or `default` if not set."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


# ── Tree views ────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def admin_tree(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    """Show the tenant/user tree with a welcome panel."""
    return _render_tree(request, db)


@router.get("/tenant/{tid}", response_class=HTMLResponse)
def admin_tenant_view(
    request: Request,
    tid: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    tenant = _load_tenant(db, tid)
    if not tenant:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    # A tenantadmin may only view their own tenant.
    if not is_superuser(_role) and tenant.tenant_id != _role.tenant_id:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    return _render_tree(request, db, selected_tenant=tenant)


@router.get("/user/{uid}", response_class=HTMLResponse)
def admin_user_view(
    request: Request,
    uid: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    user = _load_user(db, uid)
    if not user:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    # A tenantadmin may only view users in their own tenant.
    if not is_superuser(_role) and user.tenant_id != _role.tenant_id:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    return _render_tree(request, db, selected_user=user)


# ── Tenant CRUD ───────────────────────────────────────────

@router.post("/tenant", response_class=HTMLResponse)
def admin_tenant_create(
    request: Request,
    tenant_name: str = Form(...),
    tenant_key: str = Form(""),
    tenant_secret: str = Form(""),
    subdomain: str = Form(""),
    description: str = Form(""),
    role: str = Form("reader"),
    is_active: str = Form("off"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    name = (tenant_name or "").strip()
    if not name:
        return _render_tree(request, db, error="Tenant name is required.")
    if db.query(Tenant).filter(Tenant.tenant_name == name).first():
        return _render_tree(request, db, error=f"Tenant '{name}' already exists.")
    key = (tenant_key or "").strip()
    if not key:
        return _render_tree(request, db, error="Tenant key is required.")
    if db.query(Tenant).filter(Tenant.tenant_key == key).first():
        return _render_tree(request, db, error="That tenant key is already in use.")
    secret = (tenant_secret or "").strip()
    if not secret:
        return _render_tree(request, db, error="Tenant secret is required.")
    sub = (subdomain or "").strip().lower() or None
    if sub:
        if not re.fullmatch(r"[a-z0-9-]+", sub):
            return _render_tree(request, db, error="Subdomain must be lowercase letters, numbers or dashes.")
        if db.query(Tenant).filter(Tenant.subdomain == sub).first():
            return _render_tree(request, db, error="That subdomain is already in use.")
    tenant = Tenant(
        tenant_name=name,
        tenant_key=key,
        tenant_secret=secret,
        subdomain=sub,
        description=description or None,
        role=_valid_role(db, role),
        is_active=(is_active == "on"),
        created_date=_today(),
    )
    db.add(tenant)
    db.flush()
    db.commit()

    # Run Gitea provisioning on tenant creation (best-effort; retried lazily on
    # first use if Gitea is unavailable, or manually via the API endpoint
    # POST /admin/tenant/{tid}/provision-git).
    db.refresh(tenant)
    _provision_tenant_git(tenant)

    return RedirectResponse(url=f"/admin/tenant/{tenant.tenant_id}", status_code=303)


@router.post("/tenant/{tid}/provision-git", response_class=JSONResponse)
def admin_tenant_provision_git(
    request: Request,
    tid: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    """JSON API — provision a tenant's isolated Gitea user + private repos.

    Idempotent: safe to call again (returns current state if already provisioned).
    Also invoked automatically when a tenant is created in the UI.

    Returns:
        JSON: {Provisioned, tenant_id, git_username, git_cad_repo, git_docs_repo}
        or an error body with an appropriate status code.
    """
    tenant = _load_tenant(db, tid)
    if not tenant:
        return JSONResponse({"provisioned": False, "error": "tenant not found"}, status_code=404)

    ok = _provision_tenant_git(tenant)
    db.refresh(tenant)
    if not ok:
        return JSONResponse(
            {
                "provisioned": False,
                "tenant_id": tenant.tenant_id,
                "tenant_key": tenant.tenant_key,
                "error": "Gitea provisioning failed or is pending; check Gitea/API logs",
            },
            status_code=502,
        )
    return JSONResponse(
        {
            "provisioned": True,
            "tenant_id": tenant.tenant_id,
            "tenant_key": tenant.tenant_key,
            "git_username": tenant.git_username,
            "git_cad_repo": tenant.git_cad_repo,
            "git_docs_repo": tenant.git_docs_repo,
        }
    )


@router.post("/tenant/{tid}/edit", response_class=HTMLResponse)
def admin_tenant_edit(
    request: Request,
    tid: int,
    tenant_name: str = Form(...),
    tenant_key: str = Form(""),
    tenant_secret: str = Form(""),
    subdomain: str = Form(""),
    description: str = Form(""),
    role: str = Form("reader"),
    is_active: str = Form("off"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin", "superadmin"])),
):
    tenant = _load_tenant(db, tid)
    if not tenant:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)

    superuser = is_superuser(_role)
    can_edit_self = not superuser and tenant.tenant_id == _role.tenant_id

    if can_edit_self:
        sub = (subdomain or "").strip().lower() or None
        if sub:
            if not re.fullmatch(r"[a-z0-9-]+", sub):
                return _render_tree(request, db, selected_tenant=tenant, error="Subdomain must be lowercase letters, numbers or dashes.")
            clash = db.query(Tenant).filter(Tenant.subdomain == sub, Tenant.tenant_id != tenant.tenant_id).first()
            if clash:
                return _render_tree(request, db, selected_tenant=tenant, error="That subdomain is already taken.")
        tenant.subdomain = sub
        tenant.description = description or None
        tenant.is_active = (is_active == "on")
    else:
        name = (tenant_name or "").strip()
        if not name:
            return _render_tree(request, db, selected_tenant=tenant, error="Tenant name is required.")
        if db.query(Tenant).filter(Tenant.tenant_name == name, Tenant.tenant_id != tid).first():
            return _render_tree(request, db, selected_tenant=tenant, error="That tenant name is already in use.")
        key = (tenant_key or "").strip()
        if not key:
            return _render_tree(request, db, selected_tenant=tenant, error="Tenant key is required.")
        if db.query(Tenant).filter(Tenant.tenant_key == key, Tenant.tenant_id != tid).first():
            return _render_tree(request, db, selected_tenant=tenant, error="That tenant key is already in use.")
        secret = (tenant_secret or "").strip()
        if not secret:
            return _render_tree(request, db, selected_tenant=tenant, error="Tenant secret is required.")
        sub = (subdomain or "").strip().lower() or None
        if sub:
            if not re.fullmatch(r"[a-z0-9-]+", sub):
                return _render_tree(request, db, selected_tenant=tenant, error="Subdomain must be lowercase letters, numbers or dashes.")
            if db.query(Tenant).filter(Tenant.subdomain == sub, Tenant.tenant_id != tid).first():
                return _render_tree(request, db, selected_tenant=tenant, error="That subdomain is already in use.")
        tenant.tenant_name = name
        tenant.tenant_key = key
        tenant.tenant_secret = secret
        tenant.subdomain = sub
        tenant.description = description or None
        tenant.role = _valid_role(db, role)
        tenant.is_active = (is_active == "on")
    db.commit()
    return RedirectResponse(url=f"/admin/tenant/{tid}", status_code=303)


@router.post("/tenant/{tid}/delete", response_class=HTMLResponse)
def admin_tenant_delete(
    request: Request,
    tid: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_superuser),
):
    tenant = _load_tenant(db, tid)
    if not tenant:
        return RedirectResponse(url="/admin", status_code=303)
    user_count = db.query(User).filter(User.tenant_id == tid).count()
    part_count = db.query(Part).filter(Part.tenant_id == tid).count()
    if user_count or part_count:
        return _render_tree(
            request, db, selected_tenant=tenant,
            error=(
                f"Cannot delete tenant '{tenant.tenant_name}': it still has "
                f"{user_count} user(s) and {part_count} part(s). Remove them first."
            ),
        )
    db.delete(tenant)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


# ── Current-tenant management (tenant admin, not global super-admin) ──────

@router.get("/tenant", response_class=HTMLResponse)
def tenant_self_redirect():
    """Redirect /admin/tenant to /admin (Users & Tenants page)."""
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/tenant", response_class=HTMLResponse)
def tenant_self_update(
    request: Request,
    subdomain: str = Form(""),
    description: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _u: User = Depends(require_role(["tenantadmin"])),
):
    """Update the current tenant's own subdomain/description."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == _u.tenant_id).first()
    if not tenant:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    sub = (subdomain or "").strip().lower()
    if sub:
        if not re.fullmatch(r"[a-z0-9-]+", sub):
            return HTMLResponse(content=render(
                "admin/tenant_self.html", **auth_context(request, db),
                tenant=tenant, users=db.query(User).filter(User.tenant_id == tenant.tenant_id).all(),
                user_roles=role_names(db), base_domain=BASE_DOMAIN, error="Subdomain must be letters, numbers or dashes only (lowercase)."))
        clash = db.query(Tenant).filter(Tenant.subdomain == sub, Tenant.tenant_id != tenant.tenant_id).first()
        if clash:
            return HTMLResponse(content=render(
                "admin/tenant_self.html", **auth_context(request, db),
                tenant=tenant, users=db.query(User).filter(User.tenant_id == tenant.tenant_id).all(),
                user_roles=role_names(db), base_domain=BASE_DOMAIN, error="That subdomain is already taken."))
        tenant.subdomain = sub
    else:
        tenant.subdomain = None
    tenant.description = description or None
    db.commit()
    return RedirectResponse(url="/admin/tenant", status_code=303)


@router.post("/tenant/user", response_class=HTMLResponse)
def tenant_user_create(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    role: str = Form("reader"),
    is_active: str = Form("off"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _u: User = Depends(require_role(["tenantadmin"])),
):
    """Create a user inside the current tenant."""
    tenant_id = _u.tenant_id
    username = (username or "").strip()
    full_name = (full_name or "").strip()
    if not username or not full_name:
        return _tenant_self_error(request, db, tenant_id, "Username and full name are required.")
    if not password:
        return _tenant_self_error(request, db, tenant_id, "A password is required for a new user.")
    if db.query(User).filter(User.username == username).first():
        return _tenant_self_error(request, db, tenant_id, f"Username '{username}' already exists.")
    err = _enforce_one_admin_per_tenant(db, tenant_id, new_role=_valid_role(db, role))
    if err:
        return _tenant_self_error(request, db, tenant_id, err)
    user = User(
        username=username,
        full_name=full_name,
        email=email or None,
        password_hash=_hash_password(password),
        tenant_id=tenant_id,
        role=_valid_role(db, role),
        is_active=(is_active == "on"),
        created_date=_today(),
    )
    db.add(user)
    db.commit()
    return RedirectResponse(url="/admin/tenant", status_code=303)


@router.post("/tenant/user/{uid}/edit", response_class=HTMLResponse)
def tenant_user_edit(
    request: Request,
    uid: int,
    username: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(""),
    password: str = Form(""),
    role: str = Form("reader"),
    is_active: str = Form("off"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _u: User = Depends(require_role(["tenantadmin"])),
):
    """Edit a user that belongs to the current tenant."""
    user = db.query(User).filter(User.user_id == uid, User.tenant_id == _u.tenant_id).first()
    if not user:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    username = (username or "").strip()
    full_name = (full_name or "").strip()
    if not username or not full_name:
        return _tenant_self_error(request, db, _u.tenant_id, "Username and full name are required.")
    if db.query(User).filter(User.username == username, User.user_id != uid).first():
        return _tenant_self_error(request, db, _u.tenant_id, "That username is already in use.")
    new_role = _valid_role(db, role)
    # Guard the "one admin per tenant" rule before applying the change.
    err = _enforce_one_admin_per_tenant(
        db, _u.tenant_id, editing_user_id=user.user_id, new_role=new_role,
    )
    if err:
        return _tenant_self_error(request, db, _u.tenant_id, err)
    user.username = username
    user.full_name = full_name
    user.email = email or None
    user.role = new_role
    user.is_active = (is_active == "on")
    if password:
        user.password_hash = _hash_password(password)
    db.commit()
    return RedirectResponse(url="/admin/tenant", status_code=303)


@router.post("/tenant/user/{uid}/delete", response_class=HTMLResponse)
def tenant_user_delete(
    request: Request,
    uid: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _u: User = Depends(require_role(["tenantadmin"])),
):
    """Delete a user in the current tenant (cannot delete yourself)."""
    if uid == _u.user_id:
        return _tenant_self_error(request, db, _u.tenant_id, "You cannot delete your own account.")
    user = db.query(User).filter(User.user_id == uid, User.tenant_id == _u.tenant_id).first()
    if user:
        err = _enforce_one_admin_per_tenant(db, _u.tenant_id, editing_user_id=user.user_id)
        if err:
            return _tenant_self_error(request, db, _u.tenant_id, err)
        try:
            db.delete(user)
            db.commit()
        except Exception as e:
            db.rollback()
            return _tenant_self_error(request, db, _u.tenant_id,
                "Cannot delete this user: it is still referenced by other records (parts, documents, etc.).")
    return RedirectResponse(url="/admin/tenant", status_code=303)


def _tenant_self_error(request: Request, db: Session, tenant_id: int, message: str) -> HTMLResponse:
    """Re-render the tenant self-management page with an error."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    users = db.query(User).filter(User.tenant_id == tenant_id).order_by(User.username).all()
    return HTMLResponse(content=render(
        "admin/tenant_self.html",
        **auth_context(request, db),
        tenant=tenant,
        users=users,
        user_roles=role_names(db),
        base_domain=BASE_DOMAIN,
        error=message,
    ))


# ── User CRUD ─────────────────────────────────────────────

@router.post("/user", response_class=HTMLResponse)
def admin_user_create(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    tenant_id: Optional[int] = Form(None),
    role: str = Form("reader"),
    is_active: str = Form("off"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    username = (username or "").strip()
    full_name = (full_name or "").strip()
    # A tenantadmin may only create users in their own tenant.
    if not is_superuser(_role):
        tenant_id = _role.tenant_id
    if not username or not full_name:
        return _render_tree(request, db, error="Username and full name are required.")
    if not password:
        return _render_tree(request, db, error="A password is required for a new user.")
    if not db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first():
        return _render_tree(request, db, error="A valid tenant must be selected.")
    if db.query(User).filter(User.username == username).first():
        return _render_tree(request, db, error=f"Username '{username}' already exists.")
    new_role = _valid_role(db, role)
    err = _enforce_one_admin_per_tenant(db, tenant_id, new_role=new_role)
    if err:
        return _render_tree(request, db, error=err)
    user = User(
        username=username,
        full_name=full_name,
        email=email or None,
        password_hash=_hash_password(password),
        tenant_id=tenant_id,
        role=new_role,
        is_active=(is_active == "on"),
        created_date=_today(),
    )
    db.add(user)
    db.flush()
    db.commit()
    return RedirectResponse(url=f"/admin/user/{user.user_id}", status_code=303)


@router.post("/invite", response_class=HTMLResponse)
def admin_user_invite(
    request: Request,
    email: str = Form(...),
    role: str = Form("reader"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    """Invite a user by email + proposed role; they verify email + set password.

    Email is the login id. The invited user is created in a pending state
    (email_verified=0, no password) under the inviter's tenant and sent a
    verification link (shown in dev when SMTP is disabled).
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return _render_tree(request, db, error="A valid email is required.")
    if db.query(User).filter(User.email == email).first():
        return _render_tree(request, db, error=f"A user with email '{email}' already exists.")
    new_role = _valid_role(db, role)
    err = _enforce_one_admin_per_tenant(db, _role.tenant_id, new_role=new_role)
    if err:
        return _render_tree(request, db, error=err)

    full_name = email.split("@")[0]
    user = User(
        username=full_name,
        full_name=full_name,
        email=email,
        email_verified=False,
        password_hash="",
        tenant_id=_role.tenant_id,
        tenant_key=_role.tenant_key,
        role=new_role,
        is_active=True,
        created_date=_today(),
    )
    db.add(user)
    db.commit()

    from app.email_verify import send_verification_email
    from app.config import SMTP_ENABLED as _smtp_on
    link = send_verification_email(request, user, "invite")

    ctx = auth_context(request, db)
    ctx.update(error=None, info=(
        f"Invitation sent to {email}."
        + (f" (dev link: {link})" if not _smtp_on else " They should check their inbox.")
    ))
    return HTMLResponse(content=render("admin/list.html", **ctx,
                                       tenants=[t for t in db.query(Tenant).order_by(Tenant.tenant_name).all()],
                                       selected_tenant=None, selected_user=None,
                                       selected_tenant_id=None, selected_user_id=None,
                                       user_roles=role_names(db), tenant_roles=role_names(db),
                                       roles=role_rows(db), base_domain=BASE_DOMAIN,
                                       can_manage_tenants=is_superuser(_role),
                                       can_manage_roles=is_superuser(_role),
                                       user_tenant_locked=not is_superuser(_role)))


@router.post("/user/{uid}/edit", response_class=HTMLResponse)
def admin_user_edit(
    request: Request,
    uid: int,
    username: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(""),
    password: str = Form(""),
    tenant_id: Optional[int] = Form(None),
    role: str = Form("reader"),
    is_active: str = Form("off"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    user = _load_user(db, uid)
    if not user:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    # A tenantadmin may only edit users in their own tenant.
    if not is_superuser(_role):
        if user.tenant_id != _role.tenant_id:
            return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
        tenant_id = _role.tenant_id
    username = (username or "").strip()
    full_name = (full_name or "").strip()
    if not username or not full_name:
        return _render_tree(request, db, selected_user=user, error="Username and full name are required.")
    if not db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first():
        return _render_tree(request, db, selected_user=user, error="A valid tenant must be selected.")
    if db.query(User).filter(User.username == username, User.user_id != uid).first():
        return _render_tree(request, db, selected_user=user, error="That username is already in use.")
    new_role = _valid_role(db, role)
    err = _enforce_one_admin_per_tenant(
        db, tenant_id, editing_user_id=user.user_id, new_role=new_role,
    )
    if err:
        return _render_tree(request, db, selected_user=user, error=err)
    user.username = username
    user.full_name = full_name
    user.email = email or None
    user.tenant_id = tenant_id
    user.role = new_role
    user.is_active = (is_active == "on")
    if password:
        user.password_hash = _hash_password(password)
    db.commit()
    return RedirectResponse(url=f"/admin/user/{uid}", status_code=303)


@router.post("/user/{uid}/delete", response_class=HTMLResponse)
def admin_user_delete(
    request: Request,
    uid: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    user = _load_user(db, uid)
    if user:
        # A tenantadmin may only delete users in their own tenant.
        if not is_superuser(_role) and user.tenant_id != _role.tenant_id:
            return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
        err = _enforce_one_admin_per_tenant(db, user.tenant_id, editing_user_id=user.user_id)
        if err:
            return _render_tree(request, db, error=err)
        try:
            db.delete(user)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("ADMIN [USER_DELETE_FAIL] uid=%s: %s", uid, e)
            return _render_tree(
                request, db,
                error="Cannot delete this user: it is still referenced by other records (parts, documents, etc.).",
            )
    return RedirectResponse(url="/admin", status_code=303)


# ── App Settings ──────────────────────────────────────────
# Per-tenant key-value configuration managed from the UI. Settings are stored
# in the `app_settings` table, scoped by tenant_key. The tenant 'plm-iq' holds
# the global defaults; every other tenant's rows override them.


def _platform_tenant_key(db) -> Optional[str]:
    """The tenant_key of the platform/global tenant (hosts the masteradmin).

    The global settings are stored under the GLOBAL_TENANT_KEY bucket regardless
    of the platform tenant's actual key, so we only need this to identify *who*
    is the global editor (and thus edits the global bucket).
    """
    m = db.query(User).filter(
        (User.role.is_(None)) | (User.role == "superadmin"), User.tenant_id.isnot(None)
    ).first()
    if m:
        return m.tenant_key
    return None


def _current_tenant_key(request: Request, db) -> Optional[str]:
    """Resolve the settings bucket the current user edits.

    A platform (plm-iq) tenant admin edits the global defaults (GLOBAL_TENANT_KEY
    bucket); every other tenant admin edits their own tenant's override bucket.
    """
    tkey = getattr(request.state, "tenant_key", None)
    if not tkey:
        user_id = request.session.get("user_id")
        if user_id is not None:
            user = db.query(User).filter(User.user_id == user_id).first()
            if user:
                tkey = user.tenant_key
    if not tkey:
        return GLOBAL_TENANT_KEY

    # Platform tenant admins edit the global bucket, not a per-tenant override.
    if tkey == _platform_tenant_key(db):
        return GLOBAL_TENANT_KEY
    return tkey


def _all_settings(db: Session, tenant_key: str):
    """Return the merged settings for a tenant as a list of row dicts.

    Each row is {'key', 'value', 'global_value', 'source'}:
      'value'        - effective value for this tenant
      'global_value' - the underlying 'plm-iq' global default (so a tenant can
                       copy it), or None when the tenant IS the global editor
      'source' is one of:
      'tenant'  - overridden locally by this tenant
      'global'  - inherited from the 'plm-iq' global defaults
      'default' - from the in-code DEFAULT_SETTINGS fallback
    Note: when the editing tenant IS 'plm-iq', its rows are the globals.
    """
    from app.settings import (
        DEFAULT_SETTINGS, GLOBAL_TENANT_KEY as _GTK, encode_setting_value,
    )

    raw = db._db if isinstance(db, TenantScopedSession) else db

    global_rows = {r.key: r for r in raw.query(AppSetting).filter(AppSetting.tenant_key == _GTK).all()}
    tenant_rows = {r.key: r for r in raw.query(AppSetting).filter(AppSetting.tenant_key == tenant_key).all()} if tenant_key != _GTK else {}

    def _global_value(key: str) -> str:
        """The raw global value for a key (DB or in-code default)."""
        if key in global_rows:
            return global_rows[key].value
        if key in DEFAULT_SETTINGS:
            return encode_setting_value(key, DEFAULT_SETTINGS[key])
        return ""

    # Start from DEFAULT_SETTINGS so every constant is shown even if unseeded.
    out = []
    for key in DEFAULT_SETTINGS:
        if key in tenant_rows:
            row = {"key": key, "value": tenant_rows[key].value, "source": "tenant"}
        elif key in global_rows:
            row = {"key": key, "value": global_rows[key].value, "source": "global"}
        else:
            row = {"key": key, "value": encode_setting_value(key, DEFAULT_SETTINGS[key]), "source": "default"}
        # The effective value ('' when editing globals) and the tenant override only.
        row["global_value"] = None if tenant_key == _GTK else _global_value(key)
        row["tenant_value"] = tenant_rows[key].value if key in tenant_rows else ""
        out.append(row)

    # Add any DB-only keys not in DEFAULT_SETTINGS (e.g. legacy scalar settings).
    known = set(DEFAULT_SETTINGS)
    for key, row in global_rows.items():
        if key not in known:
            out.append({"key": key, "value": row.value, "global_value": None, "source": "global"})
    for key, row in tenant_rows.items():
        if key not in known:
            out.append({"key": key, "value": row.value, "global_value": _global_value(key), "source": "tenant"})

    out.sort(key=lambda r: r["key"])
    return out


@router.get("/settings", response_class=HTMLResponse)
def admin_settings(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
    error: str = "",
):
    """Show all app settings in an editable form (merged global + tenant)."""
    tkey = _current_tenant_key(request, db)
    ctx = auth_context(request, db)
    ctx["setting_rows"] = _all_settings(db, tkey)
    ctx["editing_tenant_key"] = tkey
    ctx["is_global_editor"] = (tkey == GLOBAL_TENANT_KEY)
    ctx["error"] = error
    return HTMLResponse(content=render(
        "admin/settings.html",
        **ctx,
    ))


@router.post("/settings", response_class=HTMLResponse)
async def admin_settings_save(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    """Save all setting key-value pairs for the current tenant as overrides."""
    from app.settings import (
        GLOBAL_TENANT_KEY as _GTK, DEFAULT_SETTINGS, SCALAR_SETTINGS,
    )

    tkey = _current_tenant_key(request, db)
    raw = db._db if isinstance(db, TenantScopedSession) else db
    is_global = (tkey == _GTK)

    form = await request.form()

    # "Add New Setting" form: it posts setting__new_key / setting__new_value on
    # top of the regular setting__* fields, so handle it first and skip those
    # two pseudo-fields in the loop below.
    new_key = (form.get("setting__new_key") or "").strip()
    new_value = (form.get("setting__new_value") or "").strip()
    adding_new = False
    if new_key:
        adding_new = True
        if not new_value:
            return RedirectResponse(url="/admin/settings?error=New+setting+requires+a+value", status_code=303)
        if new_key in set(DEFAULT_SETTINGS) or new_key in SCALAR_SETTINGS:
            return RedirectResponse(url="/admin/settings?error=Setting+already+exists", status_code=303)
        existing = raw.query(AppSetting).filter(
            AppSetting.tenant_key == tkey, AppSetting.key == new_key).first()
        if existing:
            return RedirectResponse(url="/admin/settings?error=Setting+already+exists", status_code=303)
        raw.add(AppSetting(tenant_key=tkey, key=new_key, value=new_value))
        # Re-render so the new row appears before any further saves below.

    for key, value in form.items():
        if key.startswith("setting__"):
            if key in ("setting__new_key", "setting__new_value"):
                continue
            setting_key = key[len("setting__"):]
            row = raw.query(AppSetting).filter(
                AppSetting.tenant_key == tkey,
                AppSetting.key == setting_key,
            ).first()
            value = (value or "").strip()

            # Validate "COUNTER_START" values are numeric before saving.
            if "COUNTER_START" in setting_key and value and not value.lstrip("-").isdigit():
                from urllib.parse import quote
                return RedirectResponse(
                    url=f"/admin/settings?error={quote(setting_key)}+must+be+a+number",
                    status_code=303,
                )

            if not value:
                # Clearing the override reverts to the global default.
                if row and not is_global:
                    raw.delete(row)
                elif row:
                    row.value = value
                continue
            if row:
                row.value = value
            else:
                raw.add(AppSetting(tenant_key=tkey, key=setting_key, value=value))
    db.commit()
    # Invalidate any cached settings for this tenant so the next request re-reads.
    invalidate_tenant_settings(tkey)
    return RedirectResponse(url="/admin/settings", status_code=303)
