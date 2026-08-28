"""Gateway application factory - the COMPOSITION ROOT of the ported backend.

``create_app()`` is where singletons meet: service instances live at module
scope in ``services/*`` (vertices, documents, edges, rules, tenants, users,
roles, validator, queries, files, registry, es, ingest, searcher, indexer),
gateway collaborators load here (settings, tenant_resolver, sessions), and
routers translate HTTP into service calls. To swap an implementation (e.g.
S3Storage for LocalFileStorage, or Redis jobs for JobRegistry), rebind the
singleton in its module - this factory and every route keep working.

Current layout: one router module (``routers/pages.py``) hosting all page
routes; feature-router splitting is prepared but intentionally deferred so
URLs stay byte-identical through the OOP port."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routers.pages import router as pages_router

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="PLM-IQ Gateway", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.middleware("http")
    async def no_html_caching(request, call_next):
        response = await call_next(request)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware("http")
    async def close_request_session(request, call_next):
        """Close the request-scoped tenant session attached during auth.

        ``_identity_ctx`` opens one tenant RLS session per request and stores it
        on ``request.state.session`` (shared with the assistant/tooling). This
        middleware closes it once the response is produced so connections are
        never leaked.
        """
        try:
            return await call_next(request)
        finally:
            session = getattr(request.state, "session", None)
            if session is not None:
                try:
                    session.close()
                except Exception:  # noqa: BLE001 - never mask the real response
                    logging.getLogger(__name__).warning("request.session.close_failed")
                request.state.session = None

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        from .routers.pages import _COMMON, _base_context, _render_default
        host = request.headers.get("host", "")
        if host.startswith("127.0.0.1"):
            return _render_default(request)
        context = _base_context(request)
        context["path"] = request.url.path
        context["message"] = (
            "The address you opened could not be matched to a PLM-IQ workspace. "
            "Please contact your system administrator."
        )
        return _COMMON.TemplateResponse(
            request,
            "not_found.html",
            context,
            status_code=404,
        )

    app.include_router(pages_router)
    return app


app = create_app()
