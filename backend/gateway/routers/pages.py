"""Page routes: edition landing page and the branded 404 page."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..resolver import resolve_host

router = APIRouter(include_in_schema=False)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_NOT_FOUND_MESSAGE = (
    "The address you opened could not be matched to a PLM-IQ workspace. "
    "Please contact your system administrator."
)


def _base_context(request: Request) -> dict[str, Any]:
    ctx = resolve_host(request.headers.get("host"))
    return {"request": request, "ctx": ctx}


@router.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    context = _base_context(request)
    if not context["ctx"].valid:
        return _render_not_found(request)
    return templates.TemplateResponse(request, "home.html", context)


@router.get("/{rest:path}", response_class=HTMLResponse)
def any_page(request: Request, rest: str) -> HTMLResponse:
    return _render_not_found(request, path=f"/{rest}")


def _render_not_found(request: Request, path: str = "") -> HTMLResponse:
    context = _base_context(request)
    context["path"] = path
    context["message"] = _NOT_FOUND_MESSAGE
    return templates.TemplateResponse(request, "not_found.html", context, status_code=404)
