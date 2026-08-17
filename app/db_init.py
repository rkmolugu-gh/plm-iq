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
    SavedQuery, WorkflowDefinition, WorkflowInstance,
    WorkflowTask, Notification, Role, Favorite, User, Tenant, IdSequence
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
        WorkflowDefinition.__table__,
        WorkflowInstance.__table__,
        WorkflowTask.__table__,
        Notification.__table__,
        Role.__table__,
        Favorite.__table__,
        IdSequence.__table__,
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

        # Ensure users.role is NOT NULL (no user should have a NULL role).
        # First, set any NULL roles to 'reader'.
        conn.exec_driver_sql(
            "UPDATE users SET role = 'reader' WHERE role IS NULL"
        )
        role_info = [r for r in conn.exec_driver_sql("PRAGMA table_info(users)").all() if r[1] == "role"]
        if role_info and role_info[0][3] == 0:  # notnull flag is 0 = nullable
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
                "role TEXT NOT NULL DEFAULT 'reader',"
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
            logger.info("Enforced users.role NOT NULL DEFAULT 'reader'")

        # Add audit columns (created_by, modified_by, created_date, modified_date)
        # to business-object tables that predate the schema update.
        _audit_tables = {
            "bom": "level",
            "costing_bom": "level",
            "engineering_change_orders": "eco_number",
            "approved_manufacturer_list": "id",
            "approved_vendor_list": "id",
            "cad_metadata": "id",
        }
        for table, _pk in _audit_tables.items():
            cols = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})").all()}
            for col, coltype in [
                ("created_by", "INTEGER REFERENCES users(user_id)"),
                ("modified_by", "INTEGER REFERENCES users(user_id)"),
                ("created_date", "DATE"),
                ("modified_date", "DATE"),
                ("number", "TEXT"),
            ]:
                if col not in cols:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
                    logger.info("Added column %s.%s", table, col)

        # Documents already has created_by / modified_by; ensure modified_date exists
        doc_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(documents)").all()}
        if "modified_date" not in doc_cols:
            conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN modified_date TEXT")
            logger.info("Added column documents.modified_date")
        if "document_number" not in doc_cols:
            conn.exec_driver_sql("ALTER TABLE documents ADD COLUMN document_number TEXT")
            logger.info("Added column documents.document_number")

        # Add is_global column to roles table
        role_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(roles)").all()}
        if "is_global" not in role_cols:
            conn.exec_driver_sql("ALTER TABLE roles ADD COLUMN is_global BOOLEAN NOT NULL DEFAULT FALSE")
            logger.info("Added column roles.is_global")

        # Backfill: mark default system roles as global so they're available to all tenants
        default_role_names = ["reader", "author", "tenantadmin", "quality", "manufacturing", "reviewer", "approver", "superadmin"]
        for rn in default_role_names:
            conn.exec_driver_sql(
                "UPDATE roles SET is_global = TRUE WHERE name = ? AND is_global = FALSE",
                (rn,),
            )
        logger.info("Backfilled is_global=TRUE for default roles")

        # Add is_global and make tenant_id nullable for workflow_definitions
        wf_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(workflow_definitions)").all()}
        if "is_global" not in wf_cols:
            conn.exec_driver_sql("ALTER TABLE workflow_definitions ADD COLUMN is_global BOOLEAN NOT NULL DEFAULT FALSE")
            logger.info("Added column workflow_definitions.is_global")

        # Backfill: mark the standard release definitions as global
        for tmpl_name in ["Standard Part Release", "ECO Approval"]:
            conn.exec_driver_sql(
                "UPDATE workflow_definitions SET is_global = TRUE, tenant_id = NULL WHERE name = ? AND is_global = FALSE",
                (tmpl_name,),
            )
        logger.info("Backfilled is_global=TRUE for standard workflow definitions")

        # Add in_workflow flag and active_workflow_instance_id to parts and engineering_change_orders
        for table in ["parts", "engineering_change_orders"]:
            cols = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})").all()}
            if "in_workflow" not in cols:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN in_workflow BOOLEAN NOT NULL DEFAULT FALSE")
                logger.info("Added column %s.in_workflow", table)
            if "active_workflow_instance_id" not in cols:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN active_workflow_instance_id INTEGER")
                logger.info("Added column %s.active_workflow_instance_id", table)

        # Backfill: set in_workflow=FALSE and clear active_workflow_instance_id for all objects.
        # (The default is already FALSE, so this is a no-op for new rows; ensures existing
        # rows are consistent after the column is added.)
        conn.exec_driver_sql("UPDATE parts SET in_workflow = FALSE, active_workflow_instance_id = NULL WHERE in_workflow IS NULL")
        conn.exec_driver_sql("UPDATE engineering_change_orders SET in_workflow = FALSE, active_workflow_instance_id = NULL WHERE in_workflow IS NULL")
        logger.info("Backfilled in_workflow=FALSE for all parts and ECOs")

    # Create workflow indexes
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wf_inst_unique_active "
            "ON workflow_instances(object_type, object_id) "
            "WHERE status IN ('DRAFT', 'IN_PROGRESS')"
        )
        # Object-id sequences (idempotent create for existing databases).
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS id_sequences ("
            "tenant_key TEXT NOT NULL, "
            "obj_type TEXT NOT NULL, "
            "prefix TEXT NOT NULL DEFAULT '', "
            "value INTEGER NOT NULL DEFAULT 1, "
            "PRIMARY KEY (tenant_key, obj_type))"
        )
    logger.info("Schema migrations complete")


def seed_database():
    """Seed the database with initial data from ``db/seed.sql``."""
    seed_file = Path(__file__).resolve().parent.parent / "db" / "seed.sql"
    if seed_file.exists():
        with engine.begin() as conn:
            sql = seed_file.read_text(encoding="utf-8")
            for stmt in sql.split(";"):
                # Strip leading SQL comment lines (-- ...) so that INSERT
                # statements preceded by a comment are not silently skipped.
                while True:
                    stmt = stmt.strip()
                    if not stmt or not stmt.startswith("--"):
                        break
                    nl = stmt.find("\n")
                    stmt = "" if nl == -1 else stmt[nl + 1:]
                if stmt:
                    try:
                        conn.exec_driver_sql(stmt)
                    except Exception as e:
                        logger.debug("Skipping statement due to error: %s", e)
        logger.info("Executed seed.sql")
    else:
        logger.warning("seed.sql not found at %s", seed_file)

    # Ensure masteradmin exists and has correct role
    _ensure_masteradmin()

    # Normalize tenant data (bring in line with role model)
    _normalize_tenants()

    logger.info("Database seeding complete")


def _ensure_masteradmin():
    """Ensure the masteradmin account exists and has superadmin role."""
    sess = SessionLocal()
    try:
        existing = sess.query(User).filter(User.username == "masteradmin").first()
        if existing:
            if existing.role != "superadmin":
                existing.role = "superadmin"
                sess.commit()
                logger.info("Ensured existing masteradmin account has superadmin role.")
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
            role="superadmin",
            is_active=True,
            created_date=today,
        ))
        sess.commit()
        logger.info("Created masteradmin account (role=superadmin, password='superadmin')")
    finally:
        sess.close()


def _normalize_tenants():
    """Bring the DB in line with the role model.

    - Ensure no user has a NULL role (set to 'reader').
    - Ensure every tenant has exactly one `tenantadmin` (promote/demote as needed).
    - Retire the legacy `admin` role row once no users reference it.
    - Rewrite any workflow template step that assigned to the retired `admin` role.
    """
    import copy as _copy
    sess = SessionLocal()
    try:
        # Fix any users with NULL role
        null_role_users = sess.query(User).filter(User.role.is_(None)).all()
        for user in null_role_users:
            user.role = "reader"
        if null_role_users:
            sess.commit()
            logger.info("Fixed %d user(s) with NULL role → 'reader'", len(null_role_users))

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
                    other.role = "reader"
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

        for t in sess.query(WorkflowDefinition).all():
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
                logger.info("Rewrote workflow definition '%s' admin → tenantadmin assignee", t.name)
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
