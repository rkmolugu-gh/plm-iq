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
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_db
from app.models import Tenant, User, Part, AppSetting
from app.models.role import role_names, role_rows
from app.routers.auth import require_user, require_role, require_superuser, auth_context, is_superuser, _hash_password
from app.template_utils import render
from app.config import BASE_DOMAIN

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")


def _today() -> str:
    return datetime.date.today().isoformat()


def _valid_role(db: Session, role: str) -> str:
    """Return `role` if it exists in the catalog, else the default 'reader'."""
    return role if role in set(role_names(db)) else "reader"


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
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    """Show the tenant/user tree with a welcome panel."""
    return _render_tree(request, db)


@router.get("/tenant/{tid}", response_class=HTMLResponse)
def admin_tenant_view(
    request: Request,
    tid: int,
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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
    subdomain: str = Form(""),
    description: str = Form(""),
    role: str = Form("reader"),
    is_active: str = Form("off"),
    db: Session = Depends(get_db),
    _role: User = Depends(require_superuser),
):
    name = (tenant_name or "").strip()
    if not name:
        return _render_tree(request, db, error="Tenant name is required.")
    if db.query(Tenant).filter(Tenant.tenant_name == name).first():
        return _render_tree(request, db, error=f"Tenant '{name}' already exists.")
    sub = (subdomain or "").strip().lower() or None
    if sub:
        if not re.fullmatch(r"[a-z0-9-]+", sub):
            return _render_tree(request, db, error="Subdomain must be lowercase letters, numbers or dashes.")
        if db.query(Tenant).filter(Tenant.subdomain == sub).first():
            return _render_tree(request, db, error="That subdomain is already in use.")
    tenant = Tenant(
        tenant_name=name,
        subdomain=sub,
        description=description or None,
        role=_valid_role(db, role),
        is_active=(is_active == "on"),
        created_date=_today(),
    )
    db.add(tenant)
    db.flush()
    db.commit()
    return RedirectResponse(url=f"/admin/tenant/{tenant.tenant_id}", status_code=303)


@router.post("/tenant/{tid}/edit", response_class=HTMLResponse)
def admin_tenant_edit(
    request: Request,
    tid: int,
    tenant_name: str = Form(...),
    subdomain: str = Form(""),
    description: str = Form(""),
    role: str = Form("reader"),
    is_active: str = Form("off"),
    db: Session = Depends(get_db),
    _role: User = Depends(require_superuser),
):
    tenant = _load_tenant(db, tid)
    if not tenant:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    name = (tenant_name or "").strip()
    if not name:
        return _render_tree(request, db, selected_tenant=tenant, error="Tenant name is required.")
    if db.query(Tenant).filter(Tenant.tenant_name == name, Tenant.tenant_id != tid).first():
        return _render_tree(request, db, selected_tenant=tenant, error="That tenant name is already in use.")
    sub = (subdomain or "").strip().lower() or None
    if sub:
        if not re.fullmatch(r"[a-z0-9-]+", sub):
            return _render_tree(request, db, selected_tenant=tenant, error="Subdomain must be lowercase letters, numbers or dashes.")
        if db.query(Tenant).filter(Tenant.subdomain == sub, Tenant.tenant_id != tid).first():
            return _render_tree(request, db, selected_tenant=tenant, error="That subdomain is already in use.")
    tenant.tenant_name = name
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
    db: Session = Depends(get_db),
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
def tenant_self(
    request: Request,
    db: Session = Depends(get_db),
    _u: User = Depends(require_role(["tenantadmin"])),
):
    """Manage the current tenant and its users.

    Available to any logged-in user of the tenant; the tenant is taken from
    the authenticated user (which the subdomain middleware has already
    scoped). Shows the tenant's details + a user list with inline CRUD.
    """
    tenant = db.query(Tenant).filter(Tenant.tenant_id == _u.tenant_id).first()
    if not tenant:
        return HTMLResponse(content=render("404.html", **auth_context(request, db)), status_code=404)
    users = db.query(User).filter(User.tenant_id == tenant.tenant_id).order_by(User.username).all()
    return HTMLResponse(content=render(
        "admin/tenant_self.html",
        **auth_context(request, db),
        tenant=tenant,
        users=users,
        user_roles=role_names(db),
        base_domain=BASE_DOMAIN,
    ))


@router.post("/tenant", response_class=HTMLResponse)
def tenant_self_update(
    request: Request,
    subdomain: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
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
# Key-value configuration managed from the UI. Settings are stored in the
# `app_settings` table and exposed as `show_inactive_users` (and future keys)
# in the template context.


def _all_settings(db: Session):
    """Return all settings as a list of (key, value) tuples."""
    rows = db.query(AppSetting).order_by(AppSetting.key).all()
    return [{"key": r.key, "value": r.value} for r in rows]


@router.get("/settings", response_class=HTMLResponse)
def admin_settings(
    request: Request,
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["tenantadmin"])),
    error: str = "",
):
    """Show all app settings in an editable form."""
    return HTMLResponse(content=render(
        "admin/settings.html",
        **auth_context(request, db),
        settings=_all_settings(db),
        error=error,
    ))


@router.post("/settings", response_class=HTMLResponse)
async def admin_settings_save(
    request: Request,
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["tenantadmin"])),
):
    """Save all setting key-value pairs from the form."""
    form = await request.form()
    for key, value in form.items():
        if key.startswith("setting__"):
            setting_key = key[len("setting__"):]
            row = db.query(AppSetting).filter(AppSetting.key == setting_key).first()
            if row:
                row.value = value
            else:
                db.add(AppSetting(key=setting_key, value=value))
    db.commit()
    return RedirectResponse(url="/admin/settings", status_code=303)
