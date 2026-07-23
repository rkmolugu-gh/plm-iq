"""PLM-IQ — FastAPI Application Entry Point."""

import logging
import logging.config
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import APP_TITLE, APP_DESCRIPTION, APP_VERSION, SECRET_KEY
from app.routers import dashboard, parts, bom, costing, eco, aml, avl, cad, documents, admin, auth, import_router, queries, workflow, roles, favorites
from app.routers.auth import _RedirectToLogin
from aisearch import router as search_router
from plmassistant.assistant_router import router as assistant_router
from app.database import engine, Base
from app.models import SavedQuery, WorkflowTemplate, WorkflowInstance, WorkflowTask, Notification, Role, Favorite, AppSetting

# Create ORM-only tables that aren't in db/schema.sql
# This is safe to run multiple times (won't recreate existing tables)
Base.metadata.create_all(bind=engine, tables=[
    SavedQuery.__table__,
    WorkflowTemplate.__table__,
    WorkflowInstance.__table__,
    WorkflowTask.__table__,
    Notification.__table__,
    Role.__table__,
    Favorite.__table__,
    AppSetting.__table__,
])

# ── Logging configuration ─────────────────────────────────────
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

_LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "aisearch": {"handlers": ["default"], "level": _log_level, "propagate": False},
        "plmassistant": {"handlers": ["default"], "level": _log_level, "propagate": False},
        "app": {"handlers": ["default"], "level": _log_level, "propagate": False},
        "uvicorn": {"handlers": ["default"], "level": _log_level, "propagate": False},
    },
}
logging.config.dictConfig(_LOGGING_CONFIG)
logger = logging.getLogger(__name__)
logger.info(f"Log level set to {_log_level}")

app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
)


@app.on_event("startup")
async def check_database():
    """Check if database is initialized and warn if not."""
    from app.database import SessionLocal
    from app.models import User
    logger = logging.getLogger(__name__)
    sess = SessionLocal()
    try:
        # Check if masteradmin exists
        admin = sess.query(User).filter(User.username == "masteradmin").first()
        if not admin:
            logger.warning(
                "Database not initialized! masteradmin user not found. "
                "Run 'python -m app.db_init' to initialize the database."
            )
    finally:
        sess.close()

# ── Session middleware ─────────────────────────────────────────
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


# ── Tenant resolution (subdomain → tenant) ───────────────────
# Resolves the request's subdomain to a Tenant and stores it on
# request.state.tenant so every downstream dependency can scope data
# to the tenant the subdomain implies.
@app.middleware("http")
async def resolve_tenant_middleware(request: Request, call_next):
    from app.database import SessionLocal
    from app.routers.auth import resolve_tenant

    db = SessionLocal()
    try:
        request.state.tenant = resolve_tenant(request, db)
    finally:
        db.close()
    return await call_next(request)


# ── Per-subdomain cookie domain ───────────────────────────────
# Rewrites the session cookie's Domain to the specific subdomain so a
# session established on tenant1.localhost is never sent to tenant2.*
# (The apex host keeps an unset Domain = current host.)
@app.middleware("http")
async def scoped_cookie_domain(request: Request, call_next):
    response = await call_next(request)
    tenant = getattr(request.state, "tenant", None)
    if tenant and tenant.subdomain:
        cookie = response.headers.get("set-cookie", "")
        if "session" in cookie and "Domain=" not in cookie:
            from urllib.parse import urlparse
            host = request.url.hostname or ""
            # host may include a port; cookie Domain must not.
            domain = host.split(":")[0]
            response.headers["set-cookie"] = f"{cookie}; Domain={domain}"
    return response


# ── Redirect-to-login middleware ───────────────────────────────
# Catches _RedirectToLogin exceptions raised by require_user()
# and redirects unauthenticated users to /login.
@app.middleware("http")
async def catch_auth_redirect(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except _RedirectToLogin as exc:
        return RedirectResponse(url=exc.location, status_code=303)


# Static files
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Register routers (auth must come first so /login and /logout
# don't require authentication themselves)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(parts.router)
app.include_router(bom.router)
app.include_router(costing.router)
app.include_router(eco.router)
app.include_router(aml.router)
app.include_router(avl.router)
app.include_router(cad.router)
app.include_router(documents.router)
app.include_router(admin.router)
app.include_router(roles.router)
app.include_router(import_router.router)
app.include_router(search_router.router)
app.include_router(assistant_router)
app.include_router(queries.router)
app.include_router(workflow.router)
app.include_router(favorites.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "version": APP_VERSION}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=_log_level.lower(),
        log_config=None,  # we manage logging ourselves via dictConfig above
    )