"""PLM-IQ — FastAPI Application Entry Point."""

import datetime
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
from app.database import engine, Base, SessionLocal
from app.models import SavedQuery, WorkflowTemplate, WorkflowInstance, WorkflowTask, Notification, Role, Favorite

# Tables in this repo are created from db/schema.sql, not via create_all.
# New ORM-only tables (e.g. saved_queries, workflow tables) are created surgically here.
Base.metadata.create_all(bind=engine, tables=[
    SavedQuery.__table__,
    WorkflowTemplate.__table__,
    WorkflowInstance.__table__,
    WorkflowTask.__table__,
    Notification.__table__,
    Role.__table__,
    Favorite.__table__,
])

# Surgically add columns introduced after the initial schema without a full
# migration framework. Idempotent: checks existing columns via PRAGMA
# (SQLite has no information_schema).
def _ensure_schema_columns():
    import logging as _logging
    _log = _logging.getLogger(__name__)
    with engine.begin() as conn:
        existing = {
            r[1] for r in conn.exec_driver_sql("PRAGMA table_info(tenants)").all()
        }
        if "subdomain" not in existing:
            # SQLite can't add a UNIQUE column to a populated table, so add
            # it nullable and enforce uniqueness separately via a partial index.
            conn.exec_driver_sql("ALTER TABLE tenants ADD COLUMN subdomain TEXT")
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_subdomain "
                "ON tenants(subdomain) WHERE subdomain IS NOT NULL"
            )
            _log.info("Added column tenants.subdomain (+ unique partial index)")

        # The global masteradmin uses a NULL `role` (the superuser signal), so the
        # column must be nullable. Older schemas declared it NOT NULL — relax it
        # via a table rebuild. We build `users_new`, copy the rows, drop the old
        # `users`, then rename `users_new` into place. We deliberately do NOT
        # rename the live `users` table first, because SQLite's ALTER TABLE RENAME
        # rewrites child FK references to the temp name (which would then dangle).
        role_info = [r for r in conn.exec_driver_sql("PRAGMA table_info(users)").all() if r[1] == "role"]
        if role_info and role_info[0][3] == 1:  # notnull flag
            conn.exec_driver_sql(
                "CREATE TABLE users_new ("
                "user_id INTEGER PRIMARY KEY, "
                "username TEXT NOT NULL UNIQUE, "
                "full_name TEXT NOT NULL, "
                "email TEXT, "
                "password_hash TEXT NOT NULL DEFAULT '', "
                "tenant_id INTEGER NOT NULL DEFAULT 1, "
                "is_active BOOLEAN NOT NULL DEFAULT TRUE, "
                "created_date DATE, "
                "role TEXT DEFAULT 'user', "
                "FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id))"
            )
            conn.exec_driver_sql(
                "INSERT INTO users_new "
                "(user_id, username, full_name, email, password_hash, tenant_id, "
                " is_active, created_date, role) "
                "SELECT user_id, username, full_name, email, password_hash, tenant_id, "
                " is_active, created_date, role FROM users"
            )
            conn.exec_driver_sql("DROP TABLE users")
            conn.exec_driver_sql("ALTER TABLE users_new RENAME TO users")
            _log.info("Relaxed users.role to nullable (for NULL-role masteradmin)")


def _ensure_workflow_indexes():
    """Idempotently create the partial unique index (one active workflow per object)."""
    import logging as _logging
    _log = _logging.getLogger(__name__)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wf_inst_unique_active "
            "ON workflow_instances(object_type, object_id) "
            "WHERE status IN ('DRAFT', 'IN_PROGRESS')"
        )


def _execute_seed_sql():
    """Execute the seed.sql file to populate initial data."""
    import logging as _logging
    _log = _logging.getLogger(__name__)
    seed_file = Path(__file__).resolve().parent.parent / "db" / "seed.sql"
    if not seed_file.exists():
        _log.warning("seed.sql not found at %s, skipping", seed_file)
        return
    with engine.begin() as conn:
        sql = seed_file.read_text(encoding="utf-8")
        # Execute each statement separately (SQLite doesn't support multi-statement exec)
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt and not stmt.startswith("--"):
                try:
                    conn.exec_driver_sql(stmt)
                except Exception as e:
                    _log.debug("Skipping statement due to error: %s", e)
    _log.info("Executed seed.sql")


def _seed_workflow_templates():
    """Idempotently seed default release templates for new tenants.

    Templates for the default tenant are seeded via seed.sql; this function
    handles any tenants created at runtime that don't yet have templates.
    """
    import logging as _logging
    from app.models import Tenant
    _log = _logging.getLogger(__name__)
    with engine.begin() as conn:
        tenants = conn.exec_driver_sql("SELECT tenant_id FROM tenants").fetchall()
    for (tid,) in tenants:
        existing = (
            SessionLocal()
            .query(WorkflowTemplate)
            .filter(WorkflowTemplate.tenant_id == tid)
            .count()
        )
        if existing:
            continue
        today = datetime.date.today().isoformat()
        part_def = {
            "stages": [
                {"name": "Engineering", "parallel": False,
                 "steps": [{"key": "eng", "name": "Engineering Review", "assignee_type": "role", "assignee": "author"}]},
                {"name": "Approvals", "parallel": True,
                 "steps": [
                     {"key": "qa", "name": "QA Approval", "assignee_type": "role", "assignee": "quality"},
                     {"key": "mfg", "name": "Mfg Approval", "assignee_type": "role", "assignee": "manufacturing"},
                 ]},
                {"name": "Release", "parallel": False,
                 "steps": [{"key": "rel", "name": "Release", "assignee_type": "role", "assignee": "tenantadmin"}]},
            ]
        }
        eco_def = {
            "stages": [
                {"name": "Review", "parallel": False,
                 "steps": [{"key": "rev", "name": "Change Review", "assignee_type": "role", "assignee": "author"}]},
                {"name": "Approvals", "parallel": True,
                 "steps": [
                     {"key": "qa", "name": "QA Approval", "assignee_type": "role", "assignee": "quality"},
                     {"key": "mfg", "name": "Mfg Approval", "assignee_type": "role", "assignee": "manufacturing"},
                 ]},
                {"name": "Release", "parallel": False,
                 "steps": [{"key": "rel", "name": "Release Change", "assignee_type": "role", "assignee": "tenantadmin"}]},
            ]
        }
        sess = SessionLocal()
        try:
            sess.add(WorkflowTemplate(name="Standard Part Release", object_type="part",
                                      definition=part_def, is_active=True, tenant_id=tid, created_at=today))
            sess.add(WorkflowTemplate(name="Standard ECO Release", object_type="eco",
                                      definition=eco_def, is_active=True, tenant_id=tid, created_at=today))
            sess.commit()
        finally:
            sess.close()
        _log.info("Seeded default workflow templates for tenant %s", tid)


def _ensure_masteradmin():
    """Ensure the masteradmin account exists and has NULL role.

    The masteradmin user is primarily seeded via seed.sql; this function
    handles repairs (e.g., ensuring NULL role) and fallback creation if needed.
    """
    import logging as _logging
    from app.models import User, Tenant
    from app.routers.auth import _hash_password
    _log = _logging.getLogger(__name__)
    sess = SessionLocal()
    try:
        existing = sess.query(User).filter(User.username == "masteradmin").first()
        if existing:
            # The masteradmin account already exists — ensure it is the global
            # superuser (NULL role), repairing any earlier seeding.
            if existing.role is not None:
                existing.role = None
                sess.commit()
                _log.info("Ensured existing masteradmin account has NULL role.")
            return
        # Fallback: create masteradmin if seed.sql didn't (e.g., empty DB)
        tenant = sess.query(Tenant).order_by(Tenant.tenant_id).first()
        if tenant is None:
            tenant = Tenant(
                tenant_name="master", subdomain=None, is_active=True,
                created_date=datetime.date.today().isoformat(),
            )
            sess.add(tenant)
            sess.flush()
        today = datetime.date.today().isoformat()
        sess.add(User(
            username="masteradmin",
            full_name="Master Admin",
            email=None,
            password_hash=_hash_password("superadmin"),
            tenant_id=tenant.tenant_id,
            role=None,
            is_active=True,
            created_date=today,
        ))
        sess.commit()
        _log.info("Created masteradmin account (role=NULL, password='superadmin')")
    finally:
        sess.close()


def _normalize_tenants():
    """Bring the DB in line with the new role model.

    - Ensure every tenant has exactly one `tenantadmin` (promote/demote as needed).
    - Retire the legacy `admin` role row once no users reference it.
    - Rewrite any workflow template step that assigned to the retired `admin` role.
    """
    import copy as _copy
    import logging as _logging
    from app.models import User, Tenant, Role, WorkflowTemplate
    _log = _logging.getLogger(__name__)
    sess = SessionLocal()
    try:
        tenants = sess.query(Tenant).order_by(Tenant.tenant_id).all()
        for tenant in tenants:
            admins = (
                sess.query(User)
                .filter(User.tenant_id == tenant.tenant_id, User.role.in_(["admin", "tenantadmin"]))
                .order_by(User.user_id)
                .all()
            )
            if admins:
                # Keep the first as tenantadmin; demote the rest to plain users.
                admins[0].role = "tenantadmin"
                for other in admins[1:]:
                    other.role = "user"
                sess.commit()
            else:
                users = (
                    sess.query(User)
                    .filter(User.tenant_id == tenant.tenant_id, User.is_active == True)  # noqa: E712
                    .order_by(User.user_id)
                    .all()
                )
                if users:
                    users[0].role = "tenantadmin"
                    sess.commit()
                    _log.info("Promoted user %s to tenantadmin for tenant %s", users[0].username, tenant.tenant_id)
                else:
                    _log.warning("Tenant %s has no users; skipping tenantadmin promotion", tenant.tenant_id)

        # Retire the legacy 'admin' role once no users reference it.
        admin_role = sess.query(Role).filter(Role.name == "admin").first()
        if admin_role:
            if sess.query(User).filter(User.role == "admin").count() == 0:
                sess.delete(admin_role)
                sess.commit()
                _log.info("Retired legacy 'admin' role (no users reference it).")
            else:
                _log.warning("Legacy 'admin' role still has users; leaving it in place.")

        # Rewrite any workflow template steps assigned to the retired 'admin' role.
        # `definition` is a JSON column; mutating the dict in place does not mark the
        # attribute dirty, so we build a fresh copy and reassign it.
        for t in sess.query(WorkflowTemplate).all():
            defn = _copy.deepcopy(t.definition or {})
            changed = False
            for stage in defn.get("stages", []) or []:
                for step in stage.get("steps", []) or []:
                    if step.get("assignee") == "admin":
                        step["assignee"] = "tenantadmin"
                        changed = True
            if changed:
                t.definition = defn
                sess.commit()
                _log.info("Rewrote workflow template '%s' admin → tenantadmin assignee", t.name)
    finally:
        sess.close()


_ensure_schema_columns()
_ensure_workflow_indexes()
_execute_seed_sql()
_seed_workflow_templates()
_ensure_masteradmin()
_normalize_tenants()

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