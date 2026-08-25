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
from datetime import date
from datetime import datetime as dt
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader
from services import (
    db,
    edge_service,
    enums,
    es_ingest_service,
    graph_rule_service,
    index_service,
    jobs,
    role_service,
    search_service,
    tenant_service,
    user_service,
    vertex_service,
)
from services.errors import ServiceError
from services.schemas import (
    EdgeCreate,
    EdgeUpdate,
    GraphRuleCreate,
    GraphRuleUpdate,
    PermissionCreate,
    PermissionUpdate,
    RoleCreate,
    RoleUpdate,
    TenantCreate,
    TenantUpdate,
    UserCreate,
    UserUpdate,
    VertexCreate,
    VertexUpdate,
)

from .. import auth, dummy_data, resolver
from ..resolver import EDITIONS

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

_GATEWAY_DIR = Path(__file__).resolve().parents[1]
_COMMON_TEMPLATES_DIR = _GATEWAY_DIR / "templates"


def _make_templates(base_dir: Path, overlay_dirs: tuple[Path, ...] = ()) -> Jinja2Templates:
    t = Jinja2Templates(directory=str(base_dir))
    t.env.auto_reload = True
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
def signin_submit(
    request: Request,
    tenant: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    remember: str = Form(""),
) -> RedirectResponse:
    """Real authentication against iam_tenant / iam_user via the services layer."""
    ctx = resolver.resolve_host(request.headers.get("host"))
    subdomain = (tenant or "").strip() or (ctx.tenant if ctx.valid else "")
    if not subdomain or not username or not password:
        return RedirectResponse("/signin?error=missing", status_code=303)
    ids = auth.authenticate(subdomain, username, password)
    if ids is None:
        return RedirectResponse("/signin?error=invalid", status_code=303)
    response = RedirectResponse("/dashboard", status_code=303)
    # 'Keep me signed in' persists the cookie across browser restarts (30 days);
    # unchecked, the cookie lives only for this browsing session.
    if remember == "on":
        response.set_cookie(
            auth._COOKIE_NAME,
            auth.encode_session(*ids),
            max_age=auth._REMEMBER_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
        )
    else:
        response.set_cookie(
            auth._COOKIE_NAME,
            auth.encode_session(*ids),
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


_GRAPH_TABS = ("vertex", "edge", "graph", "rule")


def _safe_uuid(raw: str) -> UUID | None:
    try:
        return UUID(raw)
    except (ValueError, AttributeError):
        return None


def _edition_id(raw: Any) -> enums.EditionId:
    """Accept enum members, value strings, or legacy str() noise alike."""
    if isinstance(raw, enums.EditionId):
        return raw
    return enums.EditionId(getattr(raw, "value", str(raw)))


def _opt_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ServiceError(f"'{raw}' is not a valid date (expected YYYY-MM-DD)") from None


def _parse_attributes(raw: str) -> dict[str, Any]:
    """``key=value`` per line; integer values stay ints so quantity-like
    attributes round-trip. Empty input means an empty annotation payload."""
    attributes: dict[str, Any] = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            raise ServiceError(
                "edge attributes must be one 'key=value' pair per line "
                f"(offending line: '{line}')"
            )
        attributes[key] = int(value) if value.lstrip("-").isdigit() else value
    return attributes


def _render_attributes(attributes: dict[str, Any]) -> str:
    return "\n".join(f"{k}={v}" for k, v in (attributes or {}).items())


def _vertex_label(v: dict) -> str:
    number = f"{v['prefix']}-{v['number']}" if v.get("prefix") else str(v["number"])
    revision = v.get("revision") or ""
    return f"{number}/{revision}" if revision else number


def _effective_label(e: dict) -> str:
    start, end = e.get("effective_from"), e.get("effective_to")
    if start and end:
        return f"{start} to {end}"
    if start:
        return f"{start} onward"
    return "-"


def _readonly_graph_context(tab: str, msg: str, err: str) -> dict[str, Any]:
    """Sample-data rendering for anonymous visitors: identical markup, no writes."""
    vertices = []
    for v in dummy_data.GRAPH["vertices"]:
        vertices.append({
            "number": v["number"],
            "label": f"{v['number']}/{v['revision']}" if v["revision"] else v["number"],
            "kind": v["kind"], "name": v["name"], "revision": v["revision"],
            "lifecycle": v["lifecycle"],
        })
    edges = [
        {
            "kind": e["kind"], "name": e["name"],
            "source_label": e["source_label"], "target_label": e["target_label"],
            "state": e["state"], "effective": e["effective"],
            "annotation": e.get("annotation", {}),
        }
        for e in dummy_data.GRAPH["edges"]
    ]
    return {
        "graph_live": False,
        "gv_vertices": vertices,
        "gv_edges": edges,
        "gv_rules": [],
        "tab": tab,
        "show_nav": True,
        "flash_msg": msg,
        "flash_err": err,
    }


def _graph_workspace(tenant_id: UUID, edition_id: str, request: Request, tab: str) -> dict[str, Any]:
    """Live explorer context for signed-in users: rows, edit targets, options."""
    params = request.query_params
    edit_raw = params.get("edit") or ""

    editing_vertex_row = editing_edge_row = editing_rule_row = None
    with db.tenant_session(tenant_id) as session:
        vertices_page = vertex_service.list_vertices(session, tenant_id, limit=200)
        edges_page = edge_service.list_edges(session, tenant_id, limit=200)
        rules_page = graph_rule_service.list_rules(session, limit=200)
        edit_id = _safe_uuid(edit_raw)
        if edit_id is not None:
            # find_* already returns a plain dict (or None)
            if tab == "vertex":
                editing_vertex_row = vertex_service.find_vertex(session, tenant_id, edit_id)
            elif tab == "edge":
                editing_edge_row = edge_service.find_edge(session, tenant_id, edit_id)
            elif tab == "rule":
                editing_rule_row = graph_rule_service.find_rule(session, edit_id)

    by_id = {str(v.id): v for v in vertices_page.items}
    vertex_numbers: dict[str, list[str]] = {}
    for v in vertices_page.items:
        vertex_numbers.setdefault(v.prefix, []).append(v.number)

    def label_of(vertex_id: str) -> str:
        v = by_id.get(str(vertex_id))
        return _vertex_label(v.model_dump()) if v else str(vertex_id)

    gv_vertices = []
    for v in vertices_page.items:
        row = v.model_dump(mode="json")
        gv_vertices.append({
            "id": row["id"], "prefix": row["prefix"],
            # display identifier ('EC-0042') so GView URLs resolve on the view page
            "number": f"{row['prefix']}-{row['number']}" if row["prefix"] else row["number"],
            "label": _vertex_label(row), "kind": row["kind"], "name": row["name"],
            "revision": row["revision"], "lifecycle": row["lifecycle_state"],
            "description": row["description"], "release_on": row["release_on"] or "",
            "version": row["version"], "marked_for_deletion": row["marked_for_deletion"],
        })

    gv_edges = []
    for e in edges_page.items:
        row = e.model_dump(mode="json")
        source_label, target_label = label_of(row["source_vertex_id"]), label_of(row["target_vertex_id"])
        gv_edges.append({
            "id": row["id"], "kind": row["kind"], "name": row["name"],
            "source_label": source_label, "target_label": target_label,
            "state": row["lifecycle_state"], "effective": _effective_label(row),
            "annotation": row["annotation"], "version": row["version"],
            "attributes_text": _render_attributes(row["annotation"]),
        })

    def rule_view(r) -> dict:
        d = r.model_dump(mode="json")
        qualifier = ""
        if d["scope"] == "edition" and d.get("edition_id"):
            qualifier = str(d["edition_id"])
        elif d["scope"] == "tenant" and d.get("tenant_id"):
            qualifier = "own"
        return {
            "id": d["id"],
            "scope": d["scope"], "qualifier": qualifier,
            "editable": d["scope"] == "tenant",
            "kind": d["edge_kind"],
            "source_kind": d["source_vertex_kind"], "target_kind": d["target_vertex_kind"],
            "cardinality": f'{d["source_cardinality"]} : {d["target_cardinality"]}',
            "participation": f'{d["source_participation"]} / {d["target_participation"]}',
            "source_states": ", ".join(d["source_lifecycle_states"]) or "any",
            "target_states": ", ".join(d["target_lifecycle_states"]) or "any",
            "required": [str(a) for a in d["required_edge_attributes"]],
            "duplicates": bool(d["duplicate_edges_allowed"]),
            "extensible": bool(d["allow_tenant_extension"]),
            "version": d["version"],
        }

    gv_rules = [rule_view(r) for r in rules_page.items]
    context: dict[str, Any] = {
        "graph_live": True,
        "gv_vertices": gv_vertices,
        "gv_edges": gv_edges,
        "gv_rules": gv_rules,
        "tab": tab,
        "show_nav": True,
        "flash_msg": params.get("msg") or "",
        "flash_err": params.get("err") or "",
        "edition_id": edition_id,
        "vertex_numbers": vertex_numbers,
        "vertex_kinds": [k.value for k in enums.VertexKind],
        "lifecycle_states": [s.value for s in enums.LifecycleState],
        "edge_kinds": [k.value for k in enums.EdgeKind],
        "edge_states": [s.value for s in enums.EdgeState],
        "cardinalities": [c.value for c in enums.Cardinality],
        "participations": [p.value for p in enums.Participation],
        # drag-and-drop builder: rule patterns drive the edge-kind proposals
        "builder_rules": [
            {"kind": r["kind"], "sk": r["source_kind"], "tk": r["target_kind"], "scope": r["scope"]}
            for r in gv_rules
        ],
    }

    def vertex_out(row) -> dict:
        out = dict(row)
        out["label"] = _vertex_label(out)
        out["release_on"] = out["release_on"].isoformat() if out.get("release_on") else ""
        return out

    def edge_view(row) -> dict:
        return {
            "id": str(row["id"]), "kind": getattr(row["kind"], "value", row["kind"]),
            "name": row["name"],
            "source_vertex_id": str(row["source_vertex_id"]),
            "source_vertex_kind": getattr(row["source_vertex_kind"], "value", row["source_vertex_kind"]),
            "target_vertex_id": str(row["target_vertex_id"]),
            "target_vertex_kind": getattr(row["target_vertex_kind"], "value", row["target_vertex_kind"]),
            "lifecycle_state": getattr(row["lifecycle_state"], "value", row["lifecycle_state"]),
            "effective_from": row["effective_from"].isoformat() if row["effective_from"] else "",
            "effective_to": row["effective_to"].isoformat() if row["effective_to"] else "",
            "annotation": row["annotation"] or {},
            "version": row["version"],
            "attributes_text": _render_attributes(row["annotation"] or {}),
        }

    if editing_vertex_row is not None:
        context["editing_vertex"] = vertex_out(editing_vertex_row)
    if editing_edge_row is not None:
        view = edge_view(editing_edge_row)
        context["editing_edge"] = view
        view["source_label"] = label_of(view["source_vertex_id"])
        view["target_label"] = label_of(view["target_vertex_id"])
    if editing_rule_row is not None:
        context["editing_rule"] = _rule_edit_view(editing_rule_row, tenant_id)
    return context


def _rule_edit_view(row: dict, tenant_id: UUID) -> dict:
    def val(v):
        return getattr(v, "value", v)

    scope = val(row["scope"])
    return {
        "id": str(row["id"]), "version": row["version"],
        "scope": scope,
        "editable": scope == "tenant" and row.get("tenant_id") == tenant_id,
        "kind": val(row["edge_kind"]),
        "source_kind": val(row["source_vertex_kind"]),
        "target_kind": val(row["target_vertex_kind"]),
        "source_cardinality": val(row["source_cardinality"]),
        "target_cardinality": val(row["target_cardinality"]),
        "source_participation": val(row["source_participation"]),
        "target_participation": val(row["target_participation"]),
        "duplicate_edges_allowed": bool(row["duplicate_edges_allowed"]),
        "allow_tenant_extension": bool(row["allow_tenant_extension"]),
        "source_states": [val(s) for s in (row["source_lifecycle_states"] or [])],
        "target_states": [val(s) for s in (row["target_lifecycle_states"] or [])],
        "required_text": ", ".join(row["required_edge_attributes"] or []),
    }


def _live_graph_view(tenant_id: UUID, number: str, source: str, relation: str, target: str) -> dict | None:
    with db.tenant_session(tenant_id) as session:
        vertices_page = vertex_service.list_vertices(session, tenant_id, limit=200)
        edges_page = edge_service.list_edges(session, tenant_id, limit=200)

    # Vertices travel through the view builder under their full display
    # identifier ('EC-0042'), so focus text, diagram labels, tree, filters,
    # and click links all read part-style instead of the bare number.
    def display_id(v) -> str:
        return f"{v.prefix}-{v.number}" if getattr(v, "prefix", "") else str(v.number)

    disp_by_id = {str(v.id): display_id(v) for v in vertices_page.items}
    meta_by_number: dict[str, dict] = {}
    for v in vertices_page.items:
        disp = display_id(v)
        meta_by_number[disp] = {
            "number": disp, "kind": v.kind.value if hasattr(v.kind, "value") else v.kind,
            "name": v.name, "revision": v.revision,
            "lifecycle": v.lifecycle_state.value if hasattr(v.lifecycle_state, "value") else v.lifecycle_state,
        }

    graph_edges = []
    for e in edges_page.items:
        source_disp = disp_by_id.get(str(e.source_vertex_id))
        target_disp = disp_by_id.get(str(e.target_vertex_id))
        if source_disp is None or target_disp is None:
            continue
        state = e.lifecycle_state.value if hasattr(e.lifecycle_state, "value") else e.lifecycle_state
        graph_edges.append({
            "kind": e.kind.value if hasattr(e.kind, "value") else e.kind,
            "name": e.name,
            "source": source_disp, "target": target_disp,
            "state": state,
            "effective": _effective_label({
                "effective_from": e.effective_from, "effective_to": e.effective_to,
            }),
            "annotation": e.annotation or {},
        })

    return dummy_data.build_graph_view(
        number, source=source, relation=relation, target=target,
        graph={"vertices": list(meta_by_number.values()), "edges": graph_edges},
    )


@router.get("/graph", response_class=HTMLResponse)
def graph(request: Request, tab: str = "vertex") -> HTMLResponse:
    context = _base_context(request)
    ctx = context["ctx"]
    if ctx.valid:
        tab = tab if tab in _GRAPH_TABS else "vertex"
        identity = context.get("identity")
        if identity is not None:
            context.update(_graph_workspace(UUID(identity.tenant_id), identity.edition_id, request, tab))
        else:
            context.update(_readonly_graph_context(tab, request.query_params.get("msg") or "",
                                                   request.query_params.get("err") or ""))
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
        identity = context.get("identity")
        if identity is not None:
            view = _live_graph_view(UUID(identity.tenant_id), number, source, relation, target)
        else:
            view = dummy_data.build_graph_view(number, source=source, relation=relation, target=target)
        if view is not None:
            context.update(view=view, show_nav=True)
            return _templates_for(ctx).TemplateResponse(request, "g_view.html", context)
        return _render_not_found(request, path=f"/graph/view/{number}")
    if not ctx.matched_pattern:
        return _render_default(request)
    return _render_not_found(request, path=f"/graph/view/{number}")


@router.get("/search", response_class=HTMLResponse, response_model=None)
def search_page(request: Request, q: str = "") -> HTMLResponse | RedirectResponse:
    """BM25 search over the signed-in tenant's Elasticsearch indices."""
    context = _base_context(request)
    ctx = context["ctx"]
    if not ctx.valid or context.get("identity") is None:
        if ctx.valid:
            return RedirectResponse("/signin?error=session", status_code=303)
        if not ctx.matched_pattern:
            return _render_default(request)
        return _render_not_found(request, path="/search")

    query = (q or "").strip()
    context.update(
        show_nav=True,
        search_q=query,
        q=query,
        results=[],
        total=None,
        vertex_count=None,
        edge_count=None,
        flash_err=request.query_params.get("err") or "",
    )
    if query:
        try:
            outcome = search_service.search(UUID(context["identity"].tenant_id), query)
            context.update(
                results=outcome["rows"],
                total=outcome["total"],
                vertex_count=outcome["vertices"],
                edge_count=outcome["edges"],
            )
        except ServiceError as exc:
            context["flash_err"] = str(exc)
    return _templates_for(ctx).TemplateResponse(request, "search.html", context)


def _graph_redirect(tab: str, *, msg: str = "", err: str = "", edit: str = "", key: str = "") -> RedirectResponse:
    target = f"/graph?tab={tab}"
    if edit:
        target += f"&edit={edit}"
    if key:
        target += f"&key={quote(key)}"
    if msg:
        target += f"&msg={quote(msg)}"
    if err:
        target += f"&err={quote(err)}"
    return RedirectResponse(target, status_code=303)


@router.post("/graph/vertices/create")
def graph_vertex_create(
    request: Request,
    kind: str = Form(...),
    number: str = Form(...),
    name: str = Form(...),
    prefix: str = Form("V"),
    revision: str = Form("A"),
    description: str = Form(""),
    release_on: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        data = VertexCreate(
            edition_id=_edition_id(ident.edition_id),
            kind=enums.VertexKind(kind),
            prefix=prefix.strip() or "V",
            number=number.strip(),
            name=name.strip(),
            revision=revision.strip() or "A",
            description=description.strip(),
            release_on=_opt_date(release_on),
        )
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            created = vertex_service.create_vertex(session, UUID(ident.tenant_id), data, actor=_actor(request))
        return _graph_redirect("vertex", msg=f"vertex {created.prefix}-{created.number}/{created.revision} created")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("vertex", err=str(exc))


@router.post("/graph/vertices/{vertex_id}/update")
def graph_vertex_update(
    request: Request,
    vertex_id: UUID,
    version: int = Form(...),
    name: str = Form(""),
    description: str = Form(""),
    revision: str = Form(""),
    lifecycle_state: str = Form(""),
    release_on: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    try:
        changes: dict[str, Any] = {"version": version}
        with db.tenant_session(tid) as session:
            current = vertex_service.get_vertex(session, tid, vertex_id)
            if name and name != current["name"]:
                changes["name"] = name.strip()
            if description and description != current["description"]:
                changes["description"] = description
            if revision and revision != current["revision"]:
                changes["revision"] = revision.strip()
            if lifecycle_state and lifecycle_state != getattr(current["lifecycle_state"], "value", current["lifecycle_state"]):
                changes["lifecycle_state"] = enums.LifecycleState(lifecycle_state)
            new_release = _opt_date(release_on)
            if new_release and new_release != current["release_on"]:
                changes["release_on"] = new_release
            vertex_service.update_vertex(
                session, tid, vertex_id, VertexUpdate(**changes), actor=_actor(request)
            )
        return _graph_redirect("vertex", msg="vertex saved")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("vertex", err=str(exc), edit=str(vertex_id))


@router.post("/graph/vertices/{vertex_id}/delete")
def graph_vertex_delete(request: Request, vertex_id: UUID, version: int = Form(...)) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    try:
        with db.tenant_session(tid) as session:
            vertex_service.soft_delete_vertex(session, tid, vertex_id, version=version, actor=_actor(request))
        return _graph_redirect("vertex", msg="vertex marked for deletion")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("vertex", err=str(exc))


@router.post("/graph/edges/create")
def graph_edge_create(
    request: Request,
    kind: str = Form(...),
    name: str = Form(...),
    source_vertex_id: str = Form(...),
    target_vertex_id: str = Form(...),
    lifecycle_state: str = Form(enums.EdgeState.PENDING_APPROVAL.value),
    effective_from: str = Form(""),
    effective_to: str = Form(""),
    attributes: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    source_id, target_id = _safe_uuid(source_vertex_id), _safe_uuid(target_vertex_id)
    if source_id is None or target_id is None:
        return _graph_redirect("edge", err="pick both a source and a target vertex")
    try:
        annotation = _parse_attributes(attributes)
        with db.tenant_session(tid) as session:
            source = vertex_service.get_vertex(session, tid, source_id)
            target = vertex_service.get_vertex(session, tid, target_id)
            data = EdgeCreate(
                edition_id=_edition_id(ident.edition_id),
                kind=enums.EdgeKind(kind),
                name=name.strip(),
                source_vertex_id=source_id,
                source_vertex_kind=source["kind"],
                target_vertex_id=target_id,
                target_vertex_kind=target["kind"],
                lifecycle_state=enums.EdgeState(lifecycle_state),
                effective_from=_opt_date(effective_from),
                effective_to=_opt_date(effective_to),
                annotation=annotation,
            )
            created = edge_service.create_edge(session, tid, data, actor=_actor(request))
        return _graph_redirect("edge", msg=f"edge '{created.name}' created")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("edge", err=str(exc))


@router.post("/graph/edges/{edge_id}/update")
def graph_edge_update(
    request: Request,
    edge_id: UUID,
    version: int = Form(...),
    name: str = Form(""),
    lifecycle_state: str = Form(""),
    effective_from: str = Form(""),
    effective_to: str = Form(""),
    attributes: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    try:
        annotation = _parse_attributes(attributes)
        changes: dict[str, Any] = {"version": version}
        with db.tenant_session(tid) as session:
            current = edge_service.get_edge(session, tid, edge_id)
            if name and name != current["name"]:
                changes["name"] = name.strip()
            if lifecycle_state and lifecycle_state != getattr(current["lifecycle_state"], "value", current["lifecycle_state"]):
                changes["lifecycle_state"] = enums.EdgeState(lifecycle_state)
            new_from, new_to = _opt_date(effective_from), _opt_date(effective_to)
            if new_from and new_from != current["effective_from"]:
                changes["effective_from"] = new_from
            if new_to and new_to != current["effective_to"]:
                changes["effective_to"] = new_to
            changes["annotation"] = annotation
            edge_service.update_edge(session, tid, edge_id, EdgeUpdate(**changes), actor=_actor(request))
        return _graph_redirect("edge", msg="edge saved")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("edge", err=str(exc), edit=str(edge_id))


@router.post("/graph/edges/{edge_id}/delete")
def graph_edge_delete(request: Request, edge_id: UUID) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            edge_service.delete_edge(session, UUID(ident.tenant_id), edge_id, actor=_actor(request))
        return _graph_redirect("edge", msg="edge deleted")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("edge", err=str(exc))


def _state_list(values: list[str]) -> list[enums.LifecycleState]:
    return [enums.LifecycleState(v) for v in values if v]


def _attr_list(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").replace("\n", ",").split(",") if part.strip()]


@router.post("/graph/rules/create")
def graph_rule_create(
    request: Request,
    edge_kind: str = Form(...),
    source_vertex_kind: str = Form(...),
    target_vertex_kind: str = Form(...),
    source_cardinality: str = Form("0..N"),
    target_cardinality: str = Form("0..N"),
    source_participation: str = Form("optional"),
    target_participation: str = Form("optional"),
    duplicate_edges_allowed: str = Form(""),
    allow_tenant_extension: str = Form(""),
    source_states: list[str] = Form([]),
    target_states: list[str] = Form([]),
    required_edge_attributes: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        data = GraphRuleCreate(
            scope=enums.RuleScope.TENANT,
            tenant_id=UUID(ident.tenant_id),
            edge_kind=enums.EdgeKind(edge_kind),
            source_vertex_kind=enums.VertexKind(source_vertex_kind),
            target_vertex_kind=enums.VertexKind(target_vertex_kind),
            source_cardinality=enums.Cardinality(source_cardinality),
            target_cardinality=enums.Cardinality(target_cardinality),
            source_participation=enums.Participation(source_participation),
            target_participation=enums.Participation(target_participation),
            duplicate_edges_allowed=bool(duplicate_edges_allowed),
            allow_tenant_extension=bool(allow_tenant_extension),
            source_lifecycle_states=_state_list(source_states),
            target_lifecycle_states=_state_list(target_states),
            required_edge_attributes=_attr_list(required_edge_attributes),
        )
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            created = graph_rule_service.create_rule(
                session, UUID(ident.tenant_id), data, actor=_actor(request)
            )
        note = (f"rule {created.edge_kind.value} "
                f"({created.source_vertex_kind.value} -> {created.target_vertex_kind.value}) created")
        return _graph_redirect("rule", msg=note)
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("rule", err=str(exc))


@router.post("/graph/rules/{rule_id}/update")
def graph_rule_update(
    request: Request,
    rule_id: UUID,
    version: int = Form(...),
    source_cardinality: str = Form(""),
    target_cardinality: str = Form(""),
    source_participation: str = Form(""),
    target_participation: str = Form(""),
    duplicate_edges_allowed: str = Form(""),
    allow_tenant_extension: str = Form(""),
    source_states: list[str] = Form([]),
    target_states: list[str] = Form([]),
    required_edge_attributes: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        changes: dict[str, Any] = {"version": version}
        if source_cardinality:
            changes["source_cardinality"] = enums.Cardinality(source_cardinality)
        if target_cardinality:
            changes["target_cardinality"] = enums.Cardinality(target_cardinality)
        if source_participation:
            changes["source_participation"] = enums.Participation(source_participation)
        if target_participation:
            changes["target_participation"] = enums.Participation(target_participation)
        changes["duplicate_edges_allowed"] = bool(duplicate_edges_allowed)
        changes["allow_tenant_extension"] = bool(allow_tenant_extension)
        changes["source_lifecycle_states"] = _state_list(source_states)
        changes["target_lifecycle_states"] = _state_list(target_states)
        changes["required_edge_attributes"] = _attr_list(required_edge_attributes)
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            graph_rule_service.update_rule(
                session, UUID(ident.tenant_id), rule_id,
                GraphRuleUpdate(**changes), actor=_actor(request),
            )
        return _graph_redirect("rule", msg="rule saved")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("rule", err=str(exc), edit=str(rule_id))


@router.post("/graph/rules/{rule_id}/delete")
def graph_rule_delete(request: Request, rule_id: UUID) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            graph_rule_service.delete_rule(session, UUID(ident.tenant_id), rule_id)
        return _graph_redirect("rule", msg="rule deleted")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("rule", err=str(exc))


_TENANT_TABS = ("tenants", "users", "roles", "permissions")


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
    editing_tenant = editing_user = editing_role = editing_permission = None
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
    tenant_candidates = []
    if editing_tenant is not None:
        with db.tenant_session(editing_tenant["id"]) as session:
            tenant_users = user_service.list_users(session, editing_tenant["id"], limit=200).items
        with db.admin_session() as session:
            tenant_candidates = user_service.list_users_outside_tenant(session, editing_tenant["id"])
    with db.tenant_session(tid) as session:
        users_page = user_service.list_users(session, tid, limit=200)
        roles_page = role_service.list_roles(session, tenant_id=tid, limit=200)
        user_roles = role_service.roles_by_user(session, tid)
        if tab == "users" and edit_id:
            eid = _safe_id(edit_id)
            if eid:
                editing_user = user_service.get_user(session, tid, eid)
        if tab == "roles" and edit_id:
            eid = _safe_id(edit_id)
            if eid:
                editing_role = role_service.get_role(session, eid, tenant_id=tid)

    permissions_view: list[dict[str, Any]] = []
    if tab == "permissions":
        with db.tenant_session(tid) as session:
            catalog = role_service.list_permissions(session, limit=200).items
            grants: dict[str, set[str]] = {}
            for r in roles_page.items:
                for perm in role_service.list_role_permissions(session, tid, r.id):
                    grants.setdefault(perm.code, set()).add(r.code)
            if edit_id:
                eid = _safe_id(edit_id)
                if eid:
                    editing_permission = role_service.get_permission(session, eid)
        permissions_view = [
            {
                "id": str(p.id),
                "code": p.code, "resource": p.resource, "action": p.action,
                "description": p.description,
                "roles": ", ".join(sorted(grants.get(p.code, set()))) or "\u2014",
            }
            for p in catalog
        ]

    context.update(
        show_nav=True,
        tab=tab,
        tenants=tenants_page.items,
        users=users_page.items,
        user_roles=user_roles,
        roles=list(roles_page.items),
        permissions=permissions_view,
        editions=EDITIONS,
        editing_tenant=editing_tenant,
        editing_user=editing_user,
        editing_role=editing_role,
        editing_permission=editing_permission,
        tenant_users=tenant_users,
        tenant_candidates=tenant_candidates,
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
    role: str = Form(""),
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
                           password_hash=password_hash, role=role.strip() or None),
                actor=_actor(request),
            )
        note = f"user {email} created" + (f" with role {role.strip()}" if role.strip() else "")
        return RedirectResponse(f"/admin/tenant?tab=users&msg={quote(note)}", status_code=303)
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


@router.post("/admin/tenant/permissions/create")
def permission_create_action(
    request: Request,
    code: str = Form(...),
    resource: str = Form(...),
    action: str = Form(...),
    description: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            role_service.create_permission(
                session,
                PermissionCreate(code=code.strip(), resource=resource.strip(),
                                 action=action.strip(), description=description.strip()),
                actor=_actor(request),
            )
        note = f"permission {code.strip()} created"
        return RedirectResponse(f"/admin/tenant?tab=permissions&msg={quote(note)}", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=permissions&err={quote(str(exc))}", status_code=303)


@router.post("/admin/tenant/permissions/{permission_id}/update")
def permission_update_action(
    request: Request,
    permission_id: UUID,
    code: str = Form(""),
    resource: str = Form(""),
    action: str = Form(""),
    description: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    changes: dict[str, Any] = {}
    if code.strip():
        changes["code"] = code.strip()
    if resource.strip():
        changes["resource"] = resource.strip()
    if action.strip():
        changes["action"] = action.strip()
    changes["description"] = description.strip()
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            role_service.update_permission(
                session, permission_id, PermissionUpdate(**changes), actor=_actor(request)
            )
        return RedirectResponse("/admin/tenant?tab=permissions&msg=saved", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(
            f"/admin/tenant?tab=permissions&err={quote(str(exc))}&edit={permission_id}",
            status_code=303,
        )


@router.post("/admin/tenant/permissions/{permission_id}/delete")
def permission_delete_action(request: Request, permission_id: UUID) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            role_service.delete_permission(session, permission_id)
        return RedirectResponse("/admin/tenant?tab=permissions&msg=permission deleted", status_code=303)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/tenant?tab=permissions&err={quote(str(exc))}", status_code=303)


def _format_stamp(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat(timespec="seconds")
    if isinstance(value, (int, float)) and value > 0:
        return dt.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    return "-"


def _watermark_view(entry: dict | None) -> dict | None:
    if not entry:
        return None
    return {
        "when": str(entry.get("last_indexed_on") or "").replace("T", " ")[:19],
        "mode": entry.get("mode"),
        "vertices": entry.get("vertices"),
        "edges": entry.get("edges"),
        "file": entry.get("file") or entry.get("note") or "",
    }


def _job_view(record: dict) -> dict:
    started, finished = record.get("started_at"), record.get("finished_at")
    duration = f"{finished - started:.1f}s" if started and finished else ("running…" if started else "queued")
    result = record.get("result")
    note = record.get("error")
    pill = {"queued": "lc-draft", "running": "lc-in_review", "done": "lc-released", "failed": "lc-obsolete"}.get(
        record["status"], ""
    )
    if result and record["status"] == "done":
        if "vertices" in result and "edges" in result:
            file_part = f" -> {result['file']}" if result.get("file") else (f" ({result['note']})" if result.get("note") else "")
            note = f"{result['documents']} docs ({result['vertices']} vertices / {result['edges']} edges){file_part}"
        else:
            note = (
                f"{result['documents']} docs ingested for {', '.join(result.get('tenants') or [])}"
                + ("" if result.get("indices") else " (no new indices)")
            )
    elif record["status"] == "done":
        note = "ok"
    return {
        "id": record["id"],
        "name": record["name"],
        "status": record["status"],
        "pill": pill,
        "started_at": _format_stamp(started) if started else "-",
        "duration": duration,
        "note": note or "",
    }


@router.get("/admin/index", response_class=HTMLResponse, response_model=None)
def index_admin(request: Request) -> HTMLResponse | RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    context = _base_context(request)
    params = request.query_params

    es = es_ingest_service.cluster_status()
    cat_rows = {row["index"]: row for row in es_ingest_service.indices_status()} if es["online"] else {}

    tenants_view = []
    with db.admin_session() as session:
        tenants_page = tenant_service.list_tenants(session, limit=500)
    for t in tenants_page.items:
        slug = index_service.slug_for(t.subdomain)
        vertex_row = cat_rows.get(index_service.vertex_index_name(slug))
        edge_row = cat_rows.get(index_service.edge_index_name(slug))
        latest = index_service.latest_file_for_slug(slug)
        tenants_view.append({
            "id": str(t.id),
            "name": t.name,
            "subdomain": t.subdomain,
            "slug": slug,
            "watermark": _watermark_view(index_service.get_watermark(t.id)),
            "vertex_docs": vertex_row["docs_count"] if vertex_row else None,
            "edge_docs": edge_row["docs_count"] if edge_row else None,
            "latest_file": latest["name"] if latest else None,
        })

    files_view = [
        {**f, "size_kb": round(f["size_bytes"] / 1024, 1), "modified_short": f["modified_on"].replace("T", " ")[:19]}
        for f in index_service.list_index_files()
    ]

    context.update(
        show_nav=True,
        es=es,
        es_indices=cat_rows.values(),
        tenants_index=tenants_view,
        files=files_view,
        jobs=[_job_view(j) for j in jobs.list_jobs()],
        active_jobs=jobs.any_active(),
        current_tenant_id=str(ident.tenant_id),
        can_nuke=bool(ident.is_tenant_admin),
        flash_msg=params.get("msg") or "",
        flash_err=params.get("err") or "",
    )
    return _COMMON.TemplateResponse(request, "admin_index.html", context)


@router.post("/admin/index/run")
def index_run_action(
    request: Request,
    tenant_id: str = Form(...),
    full: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = _safe_uuid(tenant_id)
    if tid is None:
        return RedirectResponse(f"/admin/index?err={quote('pick a tenant to index')}", status_code=303)
    try:
        with db.admin_session() as session:
            tenant = tenant_service.get_tenant(session, tid)
        job_id = index_service.start_index_job(tid, full=bool(full))
    except ServiceError as exc:
        return RedirectResponse(f"/admin/index?err={quote(str(exc))}", status_code=303)
    mode = "full rebuild" if full else "incremental"
    msg = f"{mode} indexing of '{tenant['subdomain']}' started (job {job_id})"
    return RedirectResponse(f"/admin/index?msg={quote(msg)}", status_code=303)


@router.post("/admin/index/ingest")
def index_ingest_action(request: Request, file: str = Form("")) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        if not es_ingest_service.ping():
            raise ServiceError(f"elasticsearch is not reachable at {es_ingest_service._es_url()}")
        name = (file or "").strip()
        path = index_service.resolve_index_file(name) if name else _latest_index_path()
        if path is None:
            raise ServiceError("no index files exist yet; run an indexing job first")
        job_id = es_ingest_service.start_ingest_job(path)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/index?err={quote(str(exc))}", status_code=303)
    msg = f"ingest of '{path.name}' started (job {job_id})"
    return RedirectResponse(f"/admin/index?msg={quote(msg)}", status_code=303)


def _latest_index_path():
    files = index_service.list_index_files()
    return index_service.resolve_index_file(files[0]["name"]) if files else None


@router.post("/admin/index/nuke/{tenant_id}")
def index_nuke_action(request: Request, tenant_id: UUID) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    if not ident.is_tenant_admin:
        return RedirectResponse(
            f"/admin/index?err={quote('only tenant administrators may nuke Elasticsearch data')}",
            status_code=303,
        )
    try:
        summary = es_ingest_service.nuke_tenant(tenant_id)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/index?err={quote(str(exc))}", status_code=303)
    removed = summary["documents_removed"]
    msg = (
        f"nuked {len(summary['deleted_indices'])} indices ({removed} documents) for "
        f"'{summary['tenant']}'; watermark cleared so the next run is a full re-index"
    )
    return RedirectResponse(f"/admin/index?msg={quote(msg)}", status_code=303)


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
