"""Page routes: edition workspace pages, sign-in preview, and branded 404.

Template ownership follows the edition-package model (strategy Section 5):

* ``gateway/<edition>/templates/`` - edition-owned pages (e.g. the workspace
  landing page). An edition may override any common template by shipping a
  file with the same logical name.
* ``gateway/templates/`` - platform-shared pages (base shell, sign-in,
  default info page, not-found).

Resolution order per request: active edition first, then common.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader
from services import db, role_service, tenant_service, user_service
from services.errors import ServiceError
from services.schemas import RoleCreate, RoleUpdate, TenantCreate, TenantUpdate, UserCreate, UserUpdate

from .. import auth, dummy_data, resolver
from ..resolver import EDITIONS

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

_GATEWAY_DIR = Path(__file__).resolve().parents[1]
_COMMON_TEMPLATES_DIR = _GATEWAY_DIR / "templates"


def _make_templates(base_dir: Path, overlay_dirs: tuple[Path, ...] = ()) -> Jinja2Templates:
    t = Jinja2Templates(directory=str(base_dir))
    loaders = [FileSystemLoader(str(d)) for d in overlay_dirs]
    if loaders:
        t.env.loader = ChoiceLoader([*loaders, t.env.loader])
    return t


_COMMON = _make_templates(_COMMON_TEMPLATES_DIR)

# Only editions that ship a package get their own loader; everyone else
# falls back to the platform-common templates until their package exists.
_EDITION_TEMPLATES = {
    name: _make_templates(_COMMON_TEMPLATES_DIR, (_GATEWAY_DIR / name / "templates",))
    for name in EDITIONS
    if (_GATEWAY_DIR / name / "templates").is_dir()
}


def _templates_for(ctx: resolver.TenantContext) -> Jinja2Templates:
    """Active edition's package when it ships one, else platform-common."""
    if ctx.valid:
        return _EDITION_TEMPLATES.get(ctx.edition, _COMMON)
    return _COMMON


def _identity_ctx(request: Request) -> tuple[Any, auth.Identity | None]:
    """Signed-in identity wins over host-derived context; None when anonymous."""
    identity = auth.load_identity(request.cookies.get(auth._COOKIE_NAME))
    if identity is None:
        return resolver.resolve_host(request.headers.get("host")), None
    ctx = resolver.TenantContext(
        tenant=identity.subdomain,
        edition=identity.edition_id,
        edition_label=identity.edition_label_,
        host=request.headers.get("host") or "",
        valid=True,
        matched_pattern=True,
    )
    return ctx, identity


def _base_context(request: Request) -> dict[str, Any]:
    ctx, identity = _identity_ctx(request)
    context: dict[str, Any] = {"request": request, "ctx": ctx}
    if identity is not None:
        # real signed-in user: profile menu, titles and pages use this
        context["user"] = {
            "name": identity.full_name,
            "role": identity.role_label,
            "email": identity.email,
            "is_admin": identity.is_tenant_admin,
        }
        context["identity"] = identity
    elif ctx.valid:
        # host-only context without a session: no fabricated identity
        context["user"] = None
    return context


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    context = _base_context(request)
    ctx = context["ctx"]
    if ctx.valid:
        return _templates_for(ctx).TemplateResponse(request, "home.html", context)
    if not ctx.matched_pattern:
        return _render_default(request)
    return _render_not_found(request)


@router.get("/signin", response_class=HTMLResponse)
def signin(request: Request) -> HTMLResponse:
    context = _base_context(request)
    ctx = context["ctx"]
    if ctx.valid:
        return _templates_for(ctx).TemplateResponse(request, "signin.html", context)
    if not ctx.matched_pattern:
        return _render_default(request)
    return _render_not_found(request, path="/signin")


@router.post("/signin")
def signin_submit(request: Request, tenant: str = Form(""), username: str = Form(""), password: str = Form("")) -> RedirectResponse:
    """Real authentication against iam_tenant / iam_user via the services layer."""
    ctx = resolver.resolve_host(request.headers.get("host"))
    subdomain = (tenant or "").strip() or (ctx.tenant if ctx.valid else "")
    if not subdomain or not username or not password:
        return RedirectResponse("/signin?error=missing", status_code=303)
    ids = auth.authenticate(subdomain, username, password)
    if ids is None:
        return RedirectResponse("/signin?error=invalid", status_code=303)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        auth._COOKIE_NAME,
        auth.encode_session(*ids),
        max_age=auth._MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/signout")
def signout(request: Request) -> RedirectResponse:
    response = RedirectResponse("/signin", status_code=303)
    response.delete_cookie(auth._COOKIE_NAME)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    context = _base_context(request)
    ctx = context["ctx"]
    if ctx.valid:
        context.update(dash=dummy_data.DASHBOARD, show_nav=True)
        return _templates_for(ctx).TemplateResponse(request, "dashboard.html", context)
    if not ctx.matched_pattern:
        return _render_default(request)
    return _render_not_found(request, path="/dashboard")


_GRAPH_TABS = ("vertex", "edge", "annotation")


@router.get("/graph", response_class=HTMLResponse)
def graph(request: Request, tab: str = "vertex") -> HTMLResponse:
    context = _base_context(request)
    ctx = context["ctx"]
    if ctx.valid:
        context.update(
            graph=dummy_data.GRAPH,
            tab=tab if tab in _GRAPH_TABS else "vertex",
            show_nav=True,
        )
        return _templates_for(ctx).TemplateResponse(request, "graph.html", context)
    if not ctx.matched_pattern:
        return _render_default(request)
    return _render_not_found(request, path="/graph")


@router.get("/graph/view/{number}", response_class=HTMLResponse)
def graph_view(
    request: Request,
    number: str,
    source: str = "",
    relation: str = "",
    target: str = "",
) -> HTMLResponse:
    context = _base_context(request)
    ctx = context["ctx"]
    if ctx.valid:
        view = dummy_data.build_graph_view(number, source=source, relation=relation, target=target)
        if view is not None:
            context.update(view=view, show_nav=True)
            return _templates_for(ctx).TemplateResponse(request, "g_view.html", context)
        return _render_not_found(request, path=f"/graph/view/{number}")
    if not ctx.matched_pattern:
        return _render_default(request)
    return _render_not_found(request, path=f"/graph/view/{number}")


_TENANT_TABS = ("tenants", "users", "roles")


def _require_identity(request: Request) -> auth.Identity | RedirectResponse:
    ctx, identity = _identity_ctx(request)
    if identity is None:
        return RedirectResponse("/signin?error=session", status_code=303)
    return identity


def _admin_context(request: Request, tab: str) -> dict[str, Any] | RedirectResponse:
    identity = _require_identity(request)
    if isinstance(identity, RedirectResponse):
        return identity
    context = _base_context(request)
    tab = tab if tab in _TENANT_TABS else "tenants"
    edit_id = request.query_params.get("edit") or ""
    msg = request.query_params.get("msg") or ""
    err = request.query_params.get("err") or ""

    tenants_page = users_page = roles_page = None
    editing_tenant = editing_user = editing_role = None
    tid = UUID(identity.tenant_id)

    def _safe_id(raw: str) -> UUID | None:
        try:
            return UUID(raw)
        except ValueError:
            return None

    with db.admin_session() as session:
        tenants_page = tenant_service.list_tenants(session, limit=200)
        if tab == "tenants" and edit_id:
            eid = _safe_id(edit_id)
            if eid:
                editing_tenant = tenant_service.get_tenant(session, eid)
    tenant_users = []
    if editing_tenant is not None:
        with db.tenant_session(editing_tenant["id"]) as session:
            tenant_users = user_service.list_users(session, editing_tenant["id"], limit=200).items
    with db.tenant_session(tid) as session:
        users_page = user_service.list_users(session, tid, limit=200)
        roles_page = role_service.list_roles(session, tenant_id=tid, limit=200)
        if tab == "users" and edit_id:
            eid = _safe_id(edit_id)
            if eid:
                editing_user = user_service.get_user(session, tid, eid)
        if tab == "roles" and edit_id:
            eid = _safe_id(edit_id)
            if eid:
                editing_role = role_service.get_role(session, eid, tenant_id=tid)

    context.update(
        show_nav=True,
        tab=tab,
        tenants=tenants_page.items,
        users=users_page.items,
        roles=list(roles_page.items),
        editions=EDITIONS,
        editing_tenant=editing_tenant,
        editing_user=editing_user,
        editing_role=editing_role,
        tenant_users=tenant_users,
        flash_msg=msg,
        flash_err=err,
    )
    return context


@router.get("/admin/tenant", response_class=HTMLResponse, response_model=None)
def tenant_admin(request: Request, tab: str = "tenants") -> HTMLResponse | RedirectResponse:
    context = _admin_context(request, tab)
    if isinstance(context, RedirectResponse):
        return context
    return _COMMON.TemplateResponse(request, "tenant.html", context)


@router.post("/admin/tenant/tenants/create")
def tenant_create_action(
    request: Request,
    subdomain: str = Form(...),
    name: str = Form(...),
    contact_email: str = Form(...),
    secret: str = Form(...),
    edition_id: str = Form("foundation"),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        with db.admin_session() as session:
            tenant_service.provision_tenant(
                session,
                TenantCreate(subdomain=subdomain, name=name, contact_email=contact_email,
                             secret=secret, edition_id=edition_id),
                actor=_actor(request),
            )
        return RedirectResponse(f"/admin/tenant?tab=tenants&msg={quote(f'tenant {name} provisioned')}", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=tenants&err={quote(str(exc))}", status_code=303)


@router.post("/admin/tenant/tenants/{tenant_id}/update")
def tenant_update_action(
    request: Request,
    tenant_id: UUID,
    version: int = Form(...),
    name: str = Form(""),
    contact_email: str = Form(""),
    status: str = Form(""),
    edition_id: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    changes: dict[str, Any] = {"version": version}
    for field in ("name", "contact_email", "status", "edition_id"):
        value = locals().get(field)
        if value:
            changes[field] = value
    try:
        with db.admin_session() as session:
            tenant_service.update_tenant(session, tenant_id, TenantUpdate(**changes), actor=_actor(request))
        return RedirectResponse("/admin/tenant?tab=tenants&msg=saved", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=tenants&err={quote(str(exc))}&edit={tenant_id}", status_code=303)


@router.post("/admin/tenant/tenants/{tenant_id}/add-user")
def tenant_add_user_action(
    request: Request,
    tenant_id: UUID,
    login_id: str = Form(...),
) -> RedirectResponse:
    """Attach an existing account (by email / login id) to the tenant."""
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        with db.admin_session() as session:
            user_service.assign_user_to_tenant(session, tenant_id, login_id, actor=_actor(request))
        return RedirectResponse(
            f"/admin/tenant?tab=tenants&edit={tenant_id}&msg={quote(f'user {login_id} added')}",
            status_code=303,
        )
    except ServiceError as exc:
        return RedirectResponse(
            f"/admin/tenant?tab=tenants&edit={tenant_id}&err={quote(str(exc))}", status_code=303
        )


@router.post("/admin/tenant/users/create")
def user_create_action(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(""),
    is_tenant_admin: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    import bcrypt

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode() if password else None
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            user_service.create_user(
                session,
                UUID(ident.tenant_id),
                UserCreate(email=email, full_name=full_name, is_tenant_admin=bool(is_tenant_admin),
                           password_hash=password_hash),
                actor=_actor(request),
            )
        return RedirectResponse("/admin/tenant?tab=users&msg=user created", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=users&err={quote(str(exc))}", status_code=303)


@router.post("/admin/tenant/users/{user_id}/update")
def user_update_action(
    request: Request,
    user_id: UUID,
    version: int = Form(...),
    full_name: str = Form(""),
    status: str = Form(""),
    password: str = Form(""),
    mfa_enabled: str = Form(""),
    is_tenant_admin: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    changes: dict[str, Any] = {"version": version}
    for field in ("full_name", "status"):
        value = locals().get(field)
        if value:
            changes[field] = value
    if password:
        import bcrypt

        changes["password_hash"] = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()
    if mfa_enabled == "on":
        changes["mfa_enabled"] = True
    if is_tenant_admin:
        changes["is_tenant_admin"] = is_tenant_admin == "on"
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            user_service.update_user(session, UUID(ident.tenant_id), user_id, UserUpdate(**changes), actor=_actor(request))
        return RedirectResponse("/admin/tenant?tab=users&msg=saved", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=users&err={quote(str(exc))}&edit={user_id}", status_code=303)


@router.post("/admin/tenant/roles/create")
def role_create_action(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    description: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            role_service.create_role(
                session, UUID(ident.tenant_id), RoleCreate(code=code, name=name, description=description),
                actor=_actor(request),
            )
        return RedirectResponse("/admin/tenant?tab=roles&msg=role created", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=roles&err={quote(str(exc))}", status_code=303)


@router.post("/admin/tenant/roles/{role_id}/update")
def role_update_action(
    request: Request,
    role_id: UUID,
    version: int = Form(...),
    name: str = Form(""),
    description: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    changes: dict[str, Any] = {"version": version}
    for field in ("name", "description"):
        value = locals().get(field)
        if value:
            changes[field] = value
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            role_service.update_role(session, UUID(ident.tenant_id), role_id, RoleUpdate(**changes), actor=_actor(request))
        return RedirectResponse("/admin/tenant?tab=roles&msg=saved", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=roles&err={quote(str(exc))}&edit={role_id}", status_code=303)


@router.post("/admin/tenant/roles/{role_id}/delete")
def role_delete_action(request: Request, role_id: UUID) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            role_service.delete_role(session, UUID(ident.tenant_id), role_id, actor=_actor(request))
        return RedirectResponse("/admin/tenant?tab=roles&msg=role deleted", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=roles&err={quote(str(exc))}", status_code=303)


def _actor(request: Request) -> str:
    ctx, identity = _identity_ctx(request)
    return identity.email if identity else (ctx.tenant if ctx.valid else "anonymous")


@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request) -> HTMLResponse:
    context = _base_context(request)
    ctx = context["ctx"]
    if not ctx.matched_pattern:
        context["ctx"] = resolver.TenantContext()
        return _templates_for(ctx).TemplateResponse(request, "help.html", context)
    if ctx.valid:
        return _templates_for(ctx).TemplateResponse(request, "help.html", context)
    return _render_not_found(request, path="/help")


@router.get("/{rest:path}", response_class=HTMLResponse)
def any_page(request: Request, rest: str) -> HTMLResponse:
    context = _base_context(request)
    if not context["ctx"].matched_pattern:
        return _render_default(request)
    return _render_not_found(request, path=f"/{rest}")


def _render_not_found(request: Request, path: str = "") -> HTMLResponse:
    context = _base_context(request)
    context["path"] = path
    context["message"] = (
        "The address you opened could not be matched to a PLM-IQ workspace. "
        "Please contact your system administrator."
    )
    return _templates_for(context["ctx"]).TemplateResponse(
        request, "not_found.html", context, status_code=404
    )


def _render_default(request: Request) -> HTMLResponse:
    context = _base_context(request)
    return _templates_for(context["ctx"]).TemplateResponse(request, "default.html", context)
