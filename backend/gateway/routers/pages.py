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

from contextlib import contextmanager

import logging
import os
import re
from datetime import date, timezone
from datetime import datetime as dt
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Form, Request, UploadFile
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader
from starlette.concurrency import run_in_threadpool
from services import db, edge_service, enums, es_client, graph_rule_service, index_service
from services.bulk_file_upload_service import bulk_uploads
from services.document_service import documents
from services.es_client import es
from services.edge_service import edges
from services.es_ingest_service import ingest
from services.file_store import files
from services.graph_query_service import queries
from services.graph_rule_service import rules
from services.index_service import indexer, watermarks
from services.jobs import registry
from services.role_service import roles
from services.rule_engine import validator
from services import setting_service
from services.search_service import searcher
from services.tenant_service import tenants
from services.user_service import users
from services.vertex_service import vertices
from services.ai_assistant_service import assistant, DEFAULT_MODEL, DEFAULT_BASE_URL
from services.errors import ServiceError
from services.schemas import (
    DocumentCreate,
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
from .. import auth, graph_view
from ..auth import DatabaseUnavailable, Identity, sessions
from ..resolver import TenantContext, tenant_resolver
from ..settings import settings as _gateway_settings
_EDITIONS = _gateway_settings.editions

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

    # Long business names / filenames blow out table columns; cap the visible
    # text at N chars with an ellipsis. The FULL value always travels in the
    # cell's title attribute, so hovering reveals everything.
    def short(value: Any, limit: int = 30) -> str:
        text = "" if value is None else str(value)
        return text if len(text) <= limit else text[:limit] + "…"

    t.env.filters["short"] = short
    return t


_COMMON = _make_templates(_COMMON_TEMPLATES_DIR)

# Only editions that ship a package get their own loader; everyone else
# falls back to the platform-common templates until their package exists.
_EDITION_TEMPLATES = {
    name: _make_templates(_COMMON_TEMPLATES_DIR, (_GATEWAY_DIR / name / "templates",))
    for name in _EDITIONS
    if (_GATEWAY_DIR / name / "templates").is_dir()
}


def _templates_for(ctx: TenantContext) -> Jinja2Templates:
    """Active edition's package when it ships one, else platform-common."""
    if ctx.valid:
        return _EDITION_TEMPLATES.get(ctx.edition, _COMMON)
    return _COMMON


def _identity_ctx(request: Request) -> tuple[Any, auth.Identity | None]:
    """Signed-in identity wins over host-derived context; None when anonymous.

    Resolution is cached on ``request.state`` so repeated calls within one
    request reuse the same ``Identity`` - and the same request-scoped tenant
    session, which is built here at auth time and attached to the identity as
    ``session`` so the assistant and tools can reuse it instead of opening
    their own (closed by the gateway's session middleware).
    """
    cached = getattr(request.state, "identity", None)
    if cached is not None or getattr(request.state, "_identity_resolved", False):
        return request.state._ctx, request.state.identity

    identity = sessions.load_identity(request.cookies.get(sessions.cookie_name))
    if identity is None:
        ctx = tenant_resolver.resolve(request.headers.get('host'))
        request.state._ctx = ctx
        request.state.identity = None
        request.state._identity_resolved = True
        return ctx, None

    # Build the request-scoped tenant session at auth time and attach it to the
    # identity so everything downstream shares one RLS-scoped connection.
    tid = UUID(identity.tenant_id)
    session = db.tenant_session_open(tid)
    request.state.session = session
    identity.session = session

    ctx = TenantContext(
        tenant=identity.subdomain,
        edition=identity.edition_id,
        edition_label=identity.edition_label_,
        host=request.headers.get("host") or "",
        valid=True,
        matched_pattern=True,
    )
    request.state._ctx = ctx
    request.state.identity = identity
    request.state._identity_resolved = True
    return ctx, identity


@contextmanager
def _request_session(request: Request):
    """Yield the request-scoped tenant session from the auth context.

    The session is built once during auth resolution (``_identity_ctx``) and
    cached on ``request.state.session`` so every DB call in the request - page
    routes, the assistant, tool handlers - reuses the SAME tenant RLS-scoped
    connection instead of opening its own. The single transaction is finalized
    (commit on success / rollback on error) by the gateway's session middleware.

    This context manager is intentionally a no-op on exit: it does not commit,
    rollback, or close - those are owned by the middleware so the whole request
    is one atomic unit over one shared connection.
    """
    session = getattr(request.state, "session", None)
    if session is None:
        # Defensive: build the session if a caller reached here without auth
        # resolution (should not happen for protected routes).
        ctx, identity = _identity_ctx(request)
        if identity is None:
            raise RuntimeError("No tenant session is available for an anonymous request.")
        session = db.tenant_session_open(UUID(identity.tenant_id))
        request.state.session = session
    yield session


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
        # Resolve the tenant's effective settings once and expose them to every
        # authenticated page (settings, dashboard, nav, etc.). Degrades silently
        # when the setting table/schema is not applied yet.
        tid = UUID(identity.tenant_id)
        setting = None
        try:
            with _request_session(request) as session:
                setting = setting_service.settings.get_for_tenant(session, tid)
        except (OperationalError, ProgrammingError):
            logger.warning("settings.unavailable", extra={"tenant": str(tid)})
        context["setting"] = setting
        context["tenant_settings"] = (
            setting_service.parse_content(setting.content) if setting else []
        )
    else:
        # No authenticated user - context is not valid for protected routes
        context["valid"] = False
        context["setting"] = None
        context["tenant_settings"] = []
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
    ctx = tenant_resolver.resolve(request.headers.get('host'))
    subdomain = (tenant or "").strip() or (ctx.tenant if ctx.valid else "")
    if not subdomain or not username or not password:
        return RedirectResponse("/signin?error=missing", status_code=303)
    try:
        ids = sessions.authenticate(subdomain, username, password)
    except DatabaseUnavailable:
        return RedirectResponse("/signin?error=db", status_code=303)
    if ids is None:
        return RedirectResponse("/signin?error=invalid", status_code=303)
    response = RedirectResponse("/dashboard", status_code=303)
    # 'Keep me signed in' persists the cookie across browser restarts (30 days);
    # unchecked, the cookie lives only for this browsing session.
    if remember == "on":
        response.set_cookie(
            sessions.cookie_name,
            sessions.encode_session(*ids),
            max_age=sessions.remember_max_age_seconds,
            httponly=True,
            samesite="lax",
        )
    else:
        response.set_cookie(
            sessions.cookie_name,
            sessions.encode_session(*ids),
            httponly=True,
            samesite="lax",
        )
    return response


@router.get("/signout")
def signout(request: Request) -> RedirectResponse:
    response = RedirectResponse("/signin", status_code=303)
    response.delete_cookie(sessions.cookie_name)
    return response


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    context = _base_context(request)
    ctx = context["ctx"]
    context.update(dash=graph_view.DASHBOARD, show_nav=True)
    return _templates_for(ctx).TemplateResponse(request, "dashboard.html", context)


_GRAPH_TABS = ("vertex", "edge", "graph", "rule", "view")


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
    """Shell rendering for anonymous visitors: empty tables, sign-in prompts."""
    return {
        "graph_live": False,
        "gv_vertices": [],
        "gv_edges": [],
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
    revising_source_row = None
    next_revision_value = ""
    with _request_session(request) as session:
        vertices_page = vertices.list(session, tenant_id, limit=200)
        edges_page = edges.list(session, tenant_id, limit=200)
        rules_page = rules.list(session, limit=200)
        edit_id = _safe_uuid(edit_raw)
        if edit_id is not None:
            # find_* already returns a plain dict (or None)
            if tab == "vertex":
                editing_vertex_row = vertices.find(session, tenant_id, edit_id)
            elif tab == "edge":
                editing_edge_row = edges.find(session, tenant_id, edit_id)
            elif tab == "rule":
                editing_rule_row = rules.find(session, edit_id)
        # ?revise=<id>: the create form becomes "revise" - same business
        # identity ({prefix}-{number}), successor revision prefilled, new row
        # on submit. One row per revision IS this data model's versioning.
        revise_id = _safe_uuid(params.get("revise") or "")
        if revise_id is not None and tab == "vertex":
            revising_source_row = vertices.find(session, tenant_id, revise_id)
            if revising_source_row is not None:
                next_revision_value = vertices.next_revision(
                    session,
                    tenant_id,
                    prefix=revising_source_row["prefix"],
                    number=revising_source_row["number"],
                )

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
    if revising_source_row is not None:
        source = vertex_out(revising_source_row)
        context["revising_vertex"] = {
            "id": source["id"], "label": source["label"], "kind": source["kind"],
            "prefix": source["prefix"], "number": source["number"], "name": source["name"],
            "description": source["description"], "revision": source["revision"],
            "next_revision": next_revision_value,
        }
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
    with _request_session(request) as session:
        vertices_page = vertices.list(session, tenant_id, limit=200)
        edges_page = edges.list(session, tenant_id, limit=200)

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

    return graph_view.build_graph_view(
        number, source=source, relation=relation, target=target,
        graph={"vertices": list(meta_by_number.values()), "edges": graph_edges},
    )


@router.get("/graph", response_class=HTMLResponse)
def graph(request: Request, tab: str = "vertex", vertex: str = "") -> HTMLResponse:
    context = _base_context(request)
    ctx = context["ctx"]
    if ctx.valid:
        tab = tab if tab in _GRAPH_TABS else "vertex"
        identity = context.get("identity")
        if identity is not None:
            context.update(_graph_workspace(UUID(identity.tenant_id), identity.edition_id, request, tab))
            if tab == "view":
                params = request.query_params
                selected = (vertex or "").strip()
                view = None
                if selected:
                    view = _live_graph_view(
                        UUID(identity.tenant_id), selected,
                        params.get("source") or "",
                        params.get("relation") or "",
                        params.get("target") or "",
                    )
                context.update(view=view, view_vertex=selected)
            elif tab == "graph":
                src = (request.query_params.get("src") or "").strip()
                if src:
                    match = next((v for v in context["gv_vertices"] if v["number"] == src), None)
                    if match:
                        context["auth_source"] = {
                            "id": match["id"], "kind": match["kind"],
                            "label": match["label"], "name": match["name"],
                        }
        else:
            context.update(_readonly_graph_context(tab, request.query_params.get("msg") or "",
                                                   request.query_params.get("err") or ""))
        return _templates_for(ctx).TemplateResponse(request, "graph.html", context)
    if not ctx.matched_pattern:
        return _render_default(request)
    return _render_not_found(request, path="/graph")


@router.get("/graph/view/{number}", response_class=HTMLResponse)
def graph_view_page(
    request: Request,
    number: str,
    source: str = "",
    relation: str = "",
    target: str = "",
) -> HTMLResponse:
    """Legacy deep links move to the explorer's Graph view tab, filters intact."""
    context = _base_context(request)
    ctx = context["ctx"]
    if not ctx.matched_pattern:
        return _render_not_found(request, path=f"/graph/view/{number}")
    qs = [f"{k}={quote(v)}" for k, v in
          (("source", source), ("relation", relation), ("target", target)) if v]
    url = "/graph?tab=view&vertex=" + quote(number)
    if qs:
        url += "&" + "&".join(qs)
    return RedirectResponse(url, status_code=303)


@router.get("/graph/vertices/search")
def graph_vertex_search(request: Request, q: str = "") -> JSONResponse:
    """BM25 vertex suggestions for the graph builder palette."""
    context = _base_context(request)
    identity = context.get("identity") if context["ctx"].valid else None
    if identity is None:
        return JSONResponse({"results": [], "error": "sign-in required"}, status_code=401)
    query = (q or "").strip()
    if len(query) < 2:
        return JSONResponse({"query": query, "results": []})
    try:
        outcome = searcher.search(UUID(identity.tenant_id), query, limit=12)
    except ServiceError as exc:
        return JSONResponse({"query": query, "results": [], "error": str(exc)})
    results = [
        {
            "id": row["id"],
            "label": row.get("display") or row["title"],
            "name": row.get("name") or "",
            "kind": row.get("kind") or "",
        }
        for row in outcome["rows"]
        if row["entity_type"] == "vertex"
    ]
    return JSONResponse({"query": query, "total": len(results), "results": results})


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
    es_status = es.cluster_status()
    watermark = _watermark_view(watermarks.get(UUID(context["identity"].tenant_id)))
    context.update(
        show_nav=True,
        search_q=query,
        q=query,
        results=[],
        total=None,
        vertex_count=None,
        edge_count=None,
        es_online=bool(es_status["online"]),
        es_version=es_status["version"],
        watermark=watermark,
        flash_err=request.query_params.get("err") or "",
    )
    if query and not context["es_online"]:
        context["flash_err"] = ""
    elif query:
        try:
            outcome = searcher.search(UUID(context["identity"].tenant_id), query)
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
            created = vertices.create(session, UUID(ident.tenant_id), data, actor=_actor(request))
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
        with _request_session(request) as session:
            current = vertices.get(session, tid, vertex_id)
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
            vertices.update(
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
        with _request_session(request) as session:
            vertices.soft_delete(session, tid, vertex_id, version=version, actor=_actor(request))
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
        with _request_session(request) as session:
            source = vertices.get(session, tid, source_id)
            target = vertices.get(session, tid, target_id)
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
            created = edges.create(session, tid, data, actor=_actor(request))
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
        with _request_session(request) as session:
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
            edges.update(session, tid, edge_id, EdgeUpdate(**changes), actor=_actor(request))
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
            edges.delete(session, UUID(ident.tenant_id), edge_id, actor=_actor(request))
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
            created = rules.create(
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
            rules.update(
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
            rules.delete(session, tenant_id, rule_id)
        return _graph_redirect("rule", msg="rule deleted")
    except (ServiceError, ValueError) as exc:
        return _graph_redirect("rule", err=str(exc))


_TENANT_TABS = ("tenants", "users", "roles", "permissions")

# ── Documents (Domain ▸ Documents) ──────────────────────────────────────────
# First TSE subtype surface: all vertex mechanics stay in the core service; this
# section only renders and routes. File bytes never flow through these handlers'
# transactions - they are stored before/between DB work and old objects are
# deleted after commit, so a failed request can never dangle a pointer.

_DOCUMENT_SORTS = {"number", "name", "revision", "state", "file_name", "size", "modified"}


def _documents_context(ident: auth.Identity, request: Request) -> dict[str, Any]:
    """Listing, edit target, and sort-link helpers for /documents."""
    params = request.query_params
    sort = params.get("sort") if params.get("sort") in _DOCUMENT_SORTS else "number"
    direction = "desc" if params.get("dir") == "desc" else "asc"
    q = (params.get("q") or "").strip()
    tid = UUID(ident.tenant_id)

    with _request_session(request) as session:
        page = documents.list(
            session,
            tid,
            number_like=q or None,
            sort=sort,
            direction=direction,
        )
        editing = None
        edit_id = _safe_uuid(params.get("edit") or "")
        if edit_id:
            editing = documents.find(session, tid, edit_id)
        # ?revise=<id>: create form becomes "revise" - same {prefix}-{number},
        # successor revision prefilled from the shared core helper.
        doc_revising = None
        revise_id = _safe_uuid(params.get("revise") or "")
        if revise_id:
            source = documents.find(session, tid, revise_id)
            if source is not None:
                doc_revising = {
                    "id": str(source["id"]), "label": f"{source['prefix']}-{source['number']}",
                    "prefix": source["prefix"], "number": source["number"],
                    "name": source["name"], "description": source["description"],
                    "revision": source["revision"],
                    "next_revision": documents.next_revision(
                        session,
                        tid,
                        prefix=source["prefix"],
                        number=source["number"],
                    ),
                }

    def _sort_link(col: str) -> str:
        next_dir = "desc" if (col == sort and direction == "asc") else "asc"
        query = f"sort={col}&dir={next_dir}"
        if q:
            query += f"&q={quote(q)}"
        return f"/documents?{query}"

    def _sort_icon(col: str) -> str:
        if col != sort:
            return ""
        return " &#9662;" if direction == "desc" else " &#9652;"

    return {
        "docs": page.items,
        "total_docs": page.total,
        "doc_q": q,
        "doc_sort": sort,
        "doc_dir": direction,
        "sort_link": _sort_link,
        "sort_icon": _sort_icon,
        "editing_document": editing,
        "doc_revising": doc_revising,
        "lifecycle_states": [s.value for s in enums.LifecycleState],
    }


def _documents_redirect(msg: str = "", err: str = "", edit: str = "") -> RedirectResponse:
    target = "/documents"
    parts = []
    if edit:
        parts.append(f"edit={edit}")
    if msg:
        parts.append(f"msg={quote(msg)}")
    if err:
        parts.append(f"err={quote(err)}")
    if parts:
        target += "?" + "&".join(parts)
    return RedirectResponse(target, status_code=303)


@router.get("/documents", response_class=HTMLResponse, response_model=None)
def documents_page(request: Request) -> HTMLResponse | RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    context = _base_context(request)
    params = request.query_params
    context.update(
        _documents_context(ident, request),
        flash_msg=params.get("msg") or "",
        flash_err=params.get("err") or "",
    )
    return _templates_for(context["ctx"]).TemplateResponse(request, "documents.html", context)


def _document_upload(upload: UploadFile | None) -> tuple[str, str | None, Any] | None:
    """Normalize an optional multipart file into file_store's upload triple.

    Browsers submit an empty filename when no file was picked; treating that
    as "no upload" keeps the create form's file input truly optional.
    """
    if upload is None or not upload.filename:
        return None
    return upload.filename, upload.content_type, upload.file


@router.post("/documents/create")
def document_create_action(
    request: Request,
    number: str = Form(...),
    name: str = Form(...),
    prefix: str = Form("DOC"),
    revision: str = Form("A"),
    description: str = Form(""),
    release_on: str = Form(""),
    file: UploadFile | None = File(None),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    try:
        data = DocumentCreate(
            edition_id=_edition_id(ident.edition_id),
            # Explicit despite the DTO default: create_vertex dumps
            # exclude_unset=True, so a defaulted kind would be dropped from
            # the INSERT and violate the core table's NOT NULL.
            kind=enums.VertexKind.DOCUMENT,
            prefix=prefix.strip() or "DOC",
            number=number.strip(),
            name=name.strip(),
            revision=revision.strip() or "A",
            description=description.strip(),
            release_on=_opt_date(release_on),
        )
        with _request_session(request) as session:
            created = documents.create(
                session,
                tid,
                data,
                actor=_actor(request),
                upload=_document_upload(file),
            )
        msg = f"document {created.prefix}-{created.number}/{created.revision} created"
        return _documents_redirect(msg=msg)
    except (ServiceError, ValueError) as exc:
        return _documents_redirect(err=str(exc))


@router.post("/documents/{vertex_id}/update")
def document_update_action(
    request: Request,
    vertex_id: UUID,
    version: int = Form(...),
    name: str = Form(""),
    description: str = Form(""),
    revision: str = Form(""),
    lifecycle_state: str = Form(""),
    release_on: str = Form(""),
    replace_file: UploadFile | None = File(None),
    remove_file: str = Form(""),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    actor = _actor(request)
    try:
        changes: dict[str, Any] = {"version": version}
        with _request_session(request) as session:
            current = documents.get(session, tid, vertex_id)
            if name and name != current["name"]:
                changes["name"] = name.strip()
            if description != "" and description != current["description"]:
                changes["description"] = description
            if revision and revision != current["revision"]:
                changes["revision"] = revision.strip()
            if lifecycle_state and lifecycle_state != getattr(current["lifecycle_state"], "value", current["lifecycle_state"]):
                changes["lifecycle_state"] = enums.LifecycleState(lifecycle_state)
            new_release = _opt_date(release_on)
            if new_release and new_release != current["release_on"]:
                changes["release_on"] = new_release

            result = documents.update(
                session, tid, vertex_id, VertexUpdate(**changes), actor=actor
            )
            # File changes apply ONLY as part of this save: the UI stages
            # removal via a hidden flag, so leaving without Save leaves the
            # stored file exactly as it was. Replacement supersedes removal
            # when both arrive.
            upload = _document_upload(replace_file)
            old_key = None
            removed = False
            if upload is not None:
                result, old_key = documents.attach_file(
                    session,
                    tid,
                    vertex_id,
                    actor,
                    filename=upload[0],
                    content_type=upload[1],
                    stream=upload[2],
                    expected_version=result.version,
                )
            elif remove_file in ("1", "true", "on") and current["storage_key"]:
                result, old_key = documents.detach_file(
                    session, tid, vertex_id, actor=actor, expected_version=result.version
                )
                removed = True
        if old_key:
            # Post-commit by construction: the tenant_session context has
            # exited, so removing the superseded object can no longer race a
            # rollback. Worst case on crash is an orphaned blob, never a
            # database row pointing at deleted bytes.
            files.delete(tid, old_key)
        msg = f"document {result.prefix}-{result.number}/{result.revision} saved"
        if removed:
            msg += "; file removed"
        return _documents_redirect(msg=msg)
    except (ServiceError, ValueError) as exc:
        return _documents_redirect(err=str(exc), edit=str(vertex_id))


@router.post("/documents/{vertex_id}/delete")
def document_delete_action(request: Request, vertex_id: UUID, version: int = Form(...)) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    try:
        with _request_session(request) as session:
            vertices.soft_delete(session, tid, vertex_id, version=version, actor=_actor(request))
        return _documents_redirect(msg="document marked for deletion")
    except (ServiceError, ValueError) as exc:
        return _documents_redirect(err=str(exc))


@router.get("/documents/next-number", response_model=None)
def document_next_number(request: Request, prefix: str = "DOC") -> JSONResponse | RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    clean = re.sub(r"[^A-Za-z0-9_-]", "", prefix.strip())
    with db.tenant_session(UUID(ident.tenant_id)) as session:
        number = documents.next_number(
            session,
            UUID(ident.tenant_id),
            prefix=clean,
        )
    return JSONResponse({"number": number})


@router.get("/documents/next-revision", response_model=None)
def document_next_revision(
    request: Request,
    prefix: str = "DOC",
    number: str = "",
) -> JSONResponse | RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    clean_prefix = re.sub(r"[^A-Za-z0-9_-]", "", prefix.strip())
    clean_number = number.strip()
    if not clean_number:
        return JSONResponse({"revision": "A"})
    try:
        with db.tenant_session(UUID(ident.tenant_id)) as session:
            revision = documents.next_revision(
                session,
                UUID(ident.tenant_id),
                prefix=clean_prefix,
                number=clean_number,
            )
    except ServiceError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return JSONResponse({"revision": revision})


@router.get("/documents/{vertex_id}/download", response_model=None)
def document_download_action(request: Request, vertex_id: UUID) -> StreamingResponse | RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    try:
        with _request_session(request) as session:
            stream, filename, mime, size = documents.download(session, tid, vertex_id)
    except ServiceError as exc:
        return _documents_redirect(err=str(exc))
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Content-Length": str(size),
    }
    return StreamingResponse(stream, media_type=mime, headers=headers)





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
        tenants_page = tenants.list(session, limit=200)
        if tab == "tenants" and edit_id:
            eid = _safe_id(edit_id)
            if eid:
                editing_tenant = tenants.get(session, eid)
    tenant_users = []
    tenant_candidates = []
    if editing_tenant is not None:
        with db.tenant_session(editing_tenant["id"]) as session:
            tenant_users = users.list(session, editing_tenant["id"], limit=200).items
        with db.admin_session() as session:
            tenant_candidates = users.list_outside_tenant(session, editing_tenant["id"])
    with _request_session(request) as session:
        users_page = users.list(session, tid, limit=200)
        roles_page = roles.list(session, tenant_id=tid, limit=200)
        user_roles = roles.roles_by_user(session, tid)
        if tab == "users" and edit_id:
            eid = _safe_id(edit_id)
            if eid:
                editing_user = users.get(session, tid, eid)
        if tab == "roles" and edit_id:
            eid = _safe_id(edit_id)
            if eid:
                editing_role = roles.get(session, eid, tenant_id=tid)

    permissions_view: list[dict[str, Any]] = []
    if tab == "permissions":
        with _request_session(request) as session:
            catalog = roles.list_permissions(session, limit=200).items
            grants: dict[str, set[str]] = {}
            for r in roles_page.items:
                for perm in roles.list_role_permissions(session, tid, r.id):
                    grants.setdefault(perm.code, set()).add(r.code)
            if edit_id:
                eid = _safe_id(edit_id)
                if eid:
                    editing_permission = roles.get_permission(session, eid)
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
        editions=_EDITIONS,
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
            tenants.provision(
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
            tenants.update(session, tenant_id, TenantUpdate(**changes), actor=_actor(request))
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
            users.assign_to_tenant(session, tenant_id, login_id, actor=_actor(request))
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
            users.create(
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
            users.update(session, UUID(ident.tenant_id), user_id, UserUpdate(**changes), actor=_actor(request))
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
            roles.create(
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
            roles.update(session, UUID(ident.tenant_id), role_id, RoleUpdate(**changes), actor=_actor(request))
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
            roles.delete(session, UUID(ident.tenant_id), role_id, actor=_actor(request))
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
            roles.create_permission(
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
            roles.update_permission(
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
            roles.delete_permission(session, permission_id)
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
    when = str(entry.get("data_as_of") or entry.get("last_indexed_on") or "")
    try:
        moment = dt.fromisoformat(when)
        when = moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        pass
    return {
        "when": when,
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


# ── Bulk file upload (Admin ▸ Bulk Upload) ─────────────────────────────────
# Folder-driven bulk import: the page collects a server-side folder, the job
# runs on the shared JobRegistry, and this same page renders the finished
# report (per-file outcome + created document numbers).


def _bulk_upload_context(ident: auth.Identity, request: Request) -> dict[str, Any]:
    params = request.query_params
    job_id = params.get("job") or ""
    job = registry.get_job(job_id) if job_id else None
    report = bulk_uploads.report(job_id) if job_id else None
    return {
        "bulk_job": job,
        "bulk_report": report,
        "bulk_jobs": bulk_uploads.recent_jobs(),
        "bulk_prefix": params.get("prefix") or "DOC",
    }


@router.get("/admin/bulk-upload", response_class=HTMLResponse, response_model=None)
def bulk_upload_page(request: Request) -> HTMLResponse | RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    context = _base_context(request)
    params = request.query_params
    context.update(
        _bulk_upload_context(ident, request),
        flash_msg=params.get("msg") or "",
        flash_err=params.get("err") or "",
    )
    return _templates_for(context["ctx"]).TemplateResponse(request, "admin_bulk_upload.html", context)


@router.post("/admin/bulk-upload/run")
def bulk_upload_run_action(
    request: Request,
    folder: str = Form(...),
    prefix: str = Form("DOC"),
) -> RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    try:
        job_id = bulk_uploads.start(
            folder,
            tenant_id=UUID(ident.tenant_id),
            edition_id=_edition_id(ident.edition_id),
            actor=_actor(request),
            prefix=prefix.strip() or "DOC",
        )
    except (ServiceError, ValueError) as exc:
        return RedirectResponse(f"/admin/bulk-upload?err={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/admin/bulk-upload?job={job_id}&msg=import+started", status_code=303)


@router.get("/admin/index", response_class=HTMLResponse, response_model=None)
def index_admin(request: Request) -> HTMLResponse | RedirectResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    context = _base_context(request)
    params = request.query_params

    es_status = es.cluster_status()
    cat_rows = {row["index"]: row for row in ingest.indices_status()} if es_status["online"] else {}

    tenants_view = []
    with db.admin_session() as session:
        tenants_page = tenants.list(session, limit=500)
    for t in tenants_page.items:
        slug = index_service.slug_for(t.subdomain)
        vertex_row = cat_rows.get(index_service.vertex_index_name(slug))
        edge_row = cat_rows.get(index_service.edge_index_name(slug))
        latest = indexer.latest_file_for_slug(slug)
        tenants_view.append({
            "id": str(t.id),
            "name": t.name,
            "subdomain": t.subdomain,
            "slug": slug,
            "watermark": _watermark_view(watermarks.get(t.id)),
            "vertex_docs": vertex_row["docs_count"] if vertex_row else None,
            "edge_docs": edge_row["docs_count"] if edge_row else None,
            "latest_file": latest["name"] if latest else None,
        })

    files_view = [
        {**f, "size_kb": round(f["size_bytes"] / 1024, 1), "modified_short": f["modified_on"].replace("T", " ")[:19]}
        for f in indexer.list_index_files()
    ]

    context.update(
        show_nav=True,
        es=es_status,
        es_indices=cat_rows.values(),
        tenants_index=tenants_view,
        files=files_view,
        jobs=[_job_view(j) for j in registry.list_jobs()],
        active_jobs=registry.any_active(),
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
            tenant = tenants.get(session, tid)
        job_id = indexer.start_index_job(tid, full=bool(full))
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
        if not es.ping():
            raise ServiceError(f"elasticsearch is not reachable at {es.url}")
        name = (file or "").strip()
        path = indexer.resolve_index_file(name) if name else _latest_index_path()
        if path is None:
            raise ServiceError("no index files exist yet; run an indexing job first")
        job_id = ingest.start_ingest_job(path)
    except ServiceError as exc:
        return RedirectResponse(f"/admin/index?err={quote(str(exc))}", status_code=303)
    msg = f"ingest of '{path.name}' started (job {job_id})"
    return RedirectResponse(f"/admin/index?msg={quote(msg)}", status_code=303)


def _latest_index_path():
    files = indexer.list_index_files()
    return indexer.resolve_index_file(files[0]["name"]) if files else None


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
        summary = ingest.nuke_tenant(tenant_id)
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
        context["ctx"] = TenantContext()
        return _templates_for(ctx).TemplateResponse(request, "help.html", context)
    if ctx.valid:
        return _templates_for(ctx).TemplateResponse(request, "help.html", context)
    return _render_not_found(request, path="/help")


# ── AI Assistant (Domain ▸ AI ▸ Assistant) ──────────────────────────────────
# The page renders the chat shell; the JSON endpoint is what the chat actually
# talks to. Both currently ride the dummy AIAssistantService, so the whole path
# works end-to-end before a real model is wired in.

@router.get("/ai-assistant", response_class=HTMLResponse)
def ai_assistant_page(request: Request) -> HTMLResponse:
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    context = _base_context(request)
    settings_map = dict(context.get("tenant_settings") or [])
    chat_model = settings_map.get("chatllmmodel") or DEFAULT_MODEL
    chat_url = settings_map.get("llmproviderurl") or DEFAULT_BASE_URL
    context.update(
        show_nav=True,
        greeting=assistant.build_greeting(ident),
        assistant_warning=not bool(os.getenv("OPENROUTER_API_KEY")),
        chat_model=chat_model,
        chat_url=chat_url,
    )
    return _templates_for(context["ctx"]).TemplateResponse(request, "ai-assistant.html", context)


@router.post("/ai-assistant/chat", response_model=None)
async def ai_assistant_chat(request: Request) -> JSONResponse:
    """Chat turn for the assistant. Forwards to OpenRouter using the tenant's
    configured model/URL and the OPENROUTER_API_KEY environment variable."""
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return JSONResponse({"detail": "sign-in required"}, status_code=401)

    message = ""
    history: list[dict[str, Any]] = []
    try:
        payload = await request.json()
        if isinstance(payload, dict):
            message = str(payload.get("message") or "")
            history = payload.get("history") or []
    except Exception:
        # Non-JSON body: tolerate a form field so the endpoint is easy to poke.
        message = (request.query_params.get("message") or "").strip()

    if not isinstance(history, list):
        history = []

    # Resolve the tenant's effective LLM settings from the shared context.
    settings_map = dict(context.get("tenant_settings") or []) if (context := _base_context(request)) else {}
    model = settings_map.get("chatllmmodel")
    base_url = settings_map.get("llmproviderurl") or settings_map.get("LLM_URL")

    result = await run_in_threadpool(
        assistant.respond,
        message,
        history=history,
        tenant=ident.tenant_id if ident else None,
        model=model,
        base_url=base_url,
        identity=ident,
        session=getattr(request.state, "session", None),
    )
    return JSONResponse(result)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    """Render the signed-in tenant's effective settings.

    Resolution is platform < tenant < user; when no row exists for this tenant
    (e.g. the schema/data has not been seeded yet) we render a friendly
    "not configured" state instead of a 404.
    """
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    context = _base_context(request)
    setting = context.get("setting")
    if setting is None:
        context.update(parsed=[], settings_error=(
            "No settings are configured for this tenant yet. "
            "Seed the setting table (platform or tenant scope) to populate this page."
        ))
        return _templates_for(context["ctx"]).TemplateResponse(
            request, "settings.html", context, status_code=200
        )

    context.update(parsed=context["tenant_settings"], settings_error=None)
    return _templates_for(context["ctx"]).TemplateResponse(
        request, "settings.html", context, status_code=200
    )


@router.post("/settings")
def settings_update(request: Request, content: str = Form("")) -> RedirectResponse:
    """Persist the edited ``.env``-style settings blob for this tenant.

    Updates the resolved setting row (platform or tenant) directly; when no row
    exists yet, a tenant-scoped override is created so the tenant can extend the
    platform defaults. Writes go through ``admin_session`` so a platform row can
    be edited (its RLS policy forbids tenant-session writes).
    """
    ident = _require_identity(request)
    if isinstance(ident, RedirectResponse):
        return ident
    tid = UUID(ident.tenant_id)
    with _request_session(request) as session:
        setting = setting_service.settings.get_for_tenant(session, tid)
    new_content = (content or "").replace("\r\n", "\n")
    try:
        with db.admin_session() as session:
            if setting is not None:
                session.execute(
                    text("UPDATE setting SET content = :c, modified_by = :m WHERE id = :id"),
                    {"c": new_content, "m": ident.email, "id": str(setting.id)},
                )
            else:
                session.execute(
                    text(
                        "INSERT INTO setting (id, level, tenant_id, user_id, content, "
                        "is_secret, created_by, modified_by) "
                        "VALUES (gen_random_uuid(), 'tenant', :tid, NULL, :c, false, :m, :m)"
                    ),
                    {"tid": str(tid), "c": new_content, "m": ident.email},
                )
    except (OperationalError, ProgrammingError):
        return RedirectResponse("/settings?error=db", status_code=303)
    return RedirectResponse("/settings", status_code=303)
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
