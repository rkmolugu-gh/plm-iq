"""Database initialization and migration module.

This module handles all database setup tasks:
- ORM table creation (for tables not in schema.sql)
- Schema migrations (for existing databases)
- Seed data insertion

This is separated from main.py so that:
1. main.py just runs the server
2. Database setup can be run separately via CLI or scripts
3. The application starts faster (no unnecessary checks on every startup)
"""

import datetime
import logging
import os
from pathlib import Path

from app.database import engine, SessionLocal
from app.models import (
    SavedQuery, WorkflowTemplate, WorkflowInstance,
    WorkflowTask, Notification, Role, Favorite, User, Tenant
)
from app.routers.auth import _hash_password

logger = logging.getLogger(__name__)


def init_orm_tables():
    """Create ORM-only tables that aren't in schema.sql.

    Tables in this repo are primarily created from db/schema.sql, not via
    create_all. This function creates only the new ORM-only tables (e.g.
    saved_queries, workflow tables) that were added after the initial schema.
    """
    from sqlalchemy import MetaData
    Base = MetaData()
    # Import all ORM models to register them
    from app import models  # noqa: F401

    # Create only the tables defined in ORM models but not in schema.sql
    # This is a surgical creation to avoid conflicts
    from app.database import Base as ORMBase
    ORMBase.metadata.create_all(bind=engine, tables=[
        SavedQuery.__table__,
        WorkflowTemplate.__table__,
        WorkflowInstance.__table__,
        WorkflowTask.__table__,
        Notification.__table__,
        Role.__table__,
        Favorite.__table__,
    ])
    logger.info("ORM tables verified/created")


def migrate_schema():
    """Run schema migrations for existing databases.

    This handles schema changes that were introduced after the initial schema
    without a full migration framework. Idempotent: checks existing columns
    via PRAGMA (SQLite has no information_schema).
    """
    # Add subdomain column to tenants if missing
    with engine.begin() as conn:
        existing = {
            r[1] for r in conn.exec_driver_sql("PRAGMA table_info(tenants)").all()
        }
        if "subdomain" not in existing:
            conn.exec_driver_sql("ALTER TABLE tenants ADD COLUMN subdomain TEXT")
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_subdomain "
                "ON tenants(subdomain) WHERE subdomain IS NOT NULL"
            )
            logger.info("Added column tenants.subdomain (+ unique partial index)")

        # Relax users.role to nullable (for NULL-role masteradmin)
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
            logger.info("Relaxed users.role to nullable (for NULL-role masteradmin)")

    # Create workflow indexes
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wf_inst_unique_active "
            "ON workflow_instances(object_type, object_id) "
            "WHERE status IN ('DRAFT', 'IN_PROGRESS')"
        )
    logger.info("Schema migrations complete")


def seed_database():
    """Seed the database with initial data.

    This executes seed.sql and then runs any additional Python-based seeding
    that requires dynamic logic (e.g., per-tenant workflow templates).
    """
    # Execute seed.sql
    seed_file = Path(__file__).resolve().parent.parent / "db" / "seed.sql"
    if seed_file.exists():
        with engine.begin() as conn:
            sql = seed_file.read_text(encoding="utf-8")
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt and not stmt.startswith("--"):
                    try:
                        conn.exec_driver_sql(stmt)
                    except Exception as e:
                        logger.debug("Skipping statement due to error: %s", e)
        logger.info("Executed seed.sql")
    else:
        logger.warning("seed.sql not found at %s", seed_file)

    # Seed workflow templates for any tenants that don't have them
    _seed_workflow_templates_for_new_tenants()

    # Ensure masteradmin exists and has correct role
    _ensure_masteradmin()

    # Normalize tenant data (bring in line with role model)
    _normalize_tenants()

    logger.info("Database seeding complete")


def _seed_workflow_templates_for_new_tenants():
    """Idempotently seed default release templates for new tenants."""
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
        logger.info("Seeded default workflow templates for tenant %s", tid)


def _ensure_masteradmin():
    """Ensure the masteradmin account exists and has NULL role."""
    sess = SessionLocal()
    try:
        existing = sess.query(User).filter(User.username == "masteradmin").first()
        if existing:
            if existing.role is not None:
                existing.role = None
                sess.commit()
                logger.info("Ensured existing masteradmin account has NULL role.")
            return
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
        logger.info("Created masteradmin account (role=NULL, password='superadmin')")
    finally:
        sess.close()


def _normalize_tenants():
    """Bring the DB in line with the new role model.

    - Ensure every tenant has exactly one `tenantadmin` (promote/demote as needed).
    - Retire the legacy `admin` role row once no users reference it.
    - Rewrite any workflow template step that assigned to the retired `admin` role.
    """
    import copy as _copy
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
                    logger.info("Promoted user %s to tenantadmin for tenant %s", users[0].username, tenant.tenant_id)
                else:
                    logger.warning("Tenant %s has no users; skipping tenantadmin promotion", tenant.tenant_id)

        admin_role = sess.query(Role).filter(Role.name == "admin").first()
        if admin_role:
            if sess.query(User).filter(User.role == "admin").count() == 0:
                sess.delete(admin_role)
                sess.commit()
                logger.info("Retired legacy 'admin' role (no users reference it).")
            else:
                logger.warning("Legacy 'admin' role still has users; leaving it in place.")

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
                logger.info("Rewrote workflow template '%s' admin → tenantadmin assignee", t.name)
    finally:
        sess.close()


def init_database():
    """Initialize the database (ORM tables + migrations + seed).

    This is the main entry point for database initialization.
    Call this from a CLI script or at startup if needed.
    """
    logger.info("Initializing database...")
    init_orm_tables()
    migrate_schema()
    seed_database()
    logger.info("Database initialization complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()
