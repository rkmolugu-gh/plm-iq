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

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, FileSystemLoader

from .. import dummy_data, resolver
from ..resolver import EDITIONS

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


def _base_context(request: Request) -> dict[str, Any]:
    ctx = resolver.resolve_host(request.headers.get("host"))
    return {"request": request, "ctx": ctx}


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
def signin_submit(request: Request) -> RedirectResponse:
    """Sign-in bypass: any credentials open the sample workspace dashboard."""
    ctx = resolver.resolve_host(request.headers.get("host"))
    target = "/dashboard" if ctx.valid else "/"
    return RedirectResponse(target, status_code=303)


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
