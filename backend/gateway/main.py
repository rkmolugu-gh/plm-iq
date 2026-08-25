"""Gateway application factory: static files + page routes + health."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
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

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(pages_router)
    return app


app = create_app()
