"""Engine, session factory, and the RLS tenant unit of work.

Every service call runs inside ``tenant_session(tenant_id)``: the transaction
first executes ``SELECT set_config('app.tenant_id', ..., true)`` so PostgreSQL
row-level security scopes every statement in that transaction to the tenant.
The setting is transaction-local; commit/rollback clears it.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_REPO_ROOT = Path(__file__).resolve().parents[2]

for _candidate in (_REPO_ROOT / ".env", _REPO_ROOT / "setup" / ".env"):
    if _candidate.is_file():
        load_dotenv(_candidate)
        break


def _database_url() -> str:
    raw = os.getenv("DATABASE_URL", "postgresql://plmiq:plmiq@localhost:5432/plmiq")
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg2://", 1)
    # .env files may carry docker-network hostnames; host-side processes
    # must target the published localhost port instead (same rewrite as createdb.bat)
    return raw.replace("@db:", "@localhost:")


engine: Engine = create_engine(
    _database_url(),
    pool_pre_ping=True,
    connect_args={"options": "-c search_path=plmiqdb,public"},
)

SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """Yield a Session whose single transaction carries the RLS tenant GUC.

    Commit on success, rollback on any exception: callers can never half-apply
    a multi-statement service operation.
    """
    with SessionLocal() as session, session.begin():
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield session


@contextmanager
def admin_session() -> Iterator[Session]:
    """Yield a plain transactional Session without the RLS tenant GUC.

    For the cross-tenant registry (iam_tenant), which deliberately carries no
    row-level security and is governed by GRANTs only (002 isolation notes).
    """
    with SessionLocal() as session, session.begin():
        yield session
