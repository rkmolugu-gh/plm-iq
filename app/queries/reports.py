"""Reports service — persistence and execution of saved queries.

A "report" is a SavedQuery row. Guided reports store a JSON builder
config in `definition`; SQL reports store the raw SQL string. Both are
re-runnable and exportable to CSV/JSON.
"""

import csv
import io
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import SavedQuery
from app.config import QUERY_MAX_ROWS
from app.queries.builder import build_guided
from app.queries.runner import run_readonly

GUIDED_ROW_CAP = QUERY_MAX_ROWS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_query(
    db: Session,
    user,
    name: str,
    description: str,
    mode: str,
    definition,
    is_public: bool = False,
) -> SavedQuery:
    """Persist a new SavedQuery. `definition` is a dict (guided) or str (sql)."""
    if not name or not name.strip():
        raise ValueError("Report name is required.")
    if mode not in ("guided", "sql"):
        raise ValueError("Invalid report mode.")

    if mode == "guided":
        def_text = json.dumps(definition, default=str)
    else:
        def_text = str(definition)

    q = SavedQuery(
        name=name.strip(),
        description=(description or "").strip() or None,
        mode=mode,
        definition=def_text,
        created_by=getattr(user, "user_id", None),
        created_at=_now(),
        is_public=bool(is_public),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def list_reports(db: Session, user) -> list[SavedQuery]:
    """Return reports owned by the user plus any public ones."""
    user_id = getattr(user, "user_id", None)
    stmt = (
        select(SavedQuery)
        .where(
            (SavedQuery.created_by == user_id) | (SavedQuery.is_public == True)  # noqa: E712
        )
        .order_by(SavedQuery.name)
    )
    return list(db.execute(stmt).scalars().all())


def get_query(db: Session, query_id: int) -> SavedQuery | None:
    return db.get(SavedQuery, query_id)


def can_edit(user, query: SavedQuery) -> bool:
    """Owner or admin may delete/modify."""
    role = getattr(user, "role", None)
    return getattr(user, "user_id", None) == query.created_by or role == "admin"


def delete_query(db: Session, user, query: SavedQuery) -> None:
    if not can_edit(user, query):
        raise PermissionError("You do not have permission to delete this report.")
    db.delete(query)
    db.commit()


def parse_definition(query: SavedQuery) -> dict | str:
    if query.mode == "guided":
        return json.loads(query.definition)
    return query.definition


def run_saved(db: Session, user, query: SavedQuery, limit: int | None = None, offset: int = 0, tenant=None) -> dict:
    """Re-run a saved report. Dispatches to guided builder or raw SQL runner."""
    if query.mode == "guided":
        cfg = json.loads(query.definition)
        cap = limit or GUIDED_ROW_CAP
        stmt, sql_str, params = build_guided(
            entity_key=cfg.get("entity"),
            columns=cfg.get("columns") or None,
            filters=cfg.get("filters") or [],
            sort=cfg.get("sort"),
            sort_dir=cfg.get("sort_dir", "asc"),
            limit=cap,
            offset=offset,
            user=user,
        )
        result = db.execute(stmt)
        columns = list(result.keys())
        rows = [list(r) for r in result.fetchall()]
        return {
            "mode": "guided",
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
            "sql": sql_str,
            "entity": cfg.get("entity"),
        }
    else:
        # SQL mode: execute on the read-only engine, scoped to the tenant.
        return run_readonly(query.definition, max_rows=limit or QUERY_MAX_ROWS, tenant=tenant)


def export_results(results: dict, fmt: str, report_name: str = "report") -> tuple[str, str]:
    """Serialize results to CSV or JSON.

    Returns (file_contents, media_type).
    """
    fmt = (fmt or "csv").lower()
    columns = results.get("columns", [])
    rows = results.get("rows", [])

    if fmt == "json":
        payload = {
            "columns": columns,
            "rows": rows,
            "row_count": results.get("row_count", len(rows)),
        }
        return json.dumps(payload, default=str, indent=2), "application/json"

    # default: CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    if columns:
        writer.writerow(columns)
    for r in rows:
        writer.writerow(["" if v is None else v for v in r])
    return buf.getvalue(), "text/csv"


def safe_filename(name: str, ext: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", name or "report").strip("_") or "report"
    return f"{base}.{ext}"
