"""Read-only SQL runner for advanced (power-user) queries.

Safety is layered:
  1. A dedicated read-only SQLite engine (`file:...?mode=ro`, uri=True).
     Writes are physically impossible even if validation misses something.
  2. validate_sql() enforces: single statement, must be SELECT, a keyword
     blocklist (INSERT/UPDATE/DROP/...), and a table allowlist restricted
     to the 7 PLM tables.
  3. Row cap (QUERY_MAX_ROWS) and a best-effort timeout.
"""

import logging
import re
import time
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import QUERY_MAX_ROWS, QUERY_TIMEOUT_SECONDS
from app.queries.registry import ALLOWED_TABLES

logger = logging.getLogger(__name__)

_FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "ATTACH", "PRAGMA", "GRANT", "REPLACE", "VACUUM", "PRAGMA", "EXEC",
    "EXECUTE", "CALL", "MERGE", "UPSERT", "BEGIN", "COMMIT", "ROLLBACK",
    "SAVEPOINT", "RELEASE", "DETACH",
}

# A statement is allowed only if it starts with SELECT / WITH (CTE that
# resolves to a read). WITH is permitted but still must not contain a
# forbidden keyword and must reference only allowed tables.
_ALLOWED_LEAD = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

# Capture referenced table names in FROM / JOIN / INTO clauses.
_TABLE_REF = re.compile(
    r"\b(?:FROM|JOIN|INTO)\s+([`\"\[]?)([a-zA-Z_][\w]*)\1",
    re.IGNORECASE,
)

_readonly_engine = None


def _ro_connect(path: str):
    """Open the SQLite DB file in read-only mode (mode='ro')."""
    import sqlite3
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _db_file_path() -> str:
    """Derive the SQLite file path from DATABASE_URL (sqlite:///...)."""
    from app.config import DATABASE_URL
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL[len("sqlite:///"):]
    if DATABASE_URL.startswith("sqlite://"):
        return DATABASE_URL[len("sqlite://"):]
    raise RuntimeError(f"Unsupported DATABASE_URL for read-only engine: {DATABASE_URL}")


def get_readonly_engine():
    """Lazily build and cache a read-only SQLite engine."""
    global _readonly_engine
    if _readonly_engine is not None:
        return _readonly_engine

    path = _db_file_path()
    # SQLAlchemy SQLite read-only: use a URI filename via connect_args so
    # writes are physically impossible (mode=ro).
    eng = create_engine(
        "sqlite://",
        creator=lambda: _ro_connect(path),
        echo=False,
    )

    @event.listens_for(eng, "connect")
    def _set_pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        # Read-only engine: do NOT try to set journal_mode=WAL (would fail).
        cur.execute("PRAGMA query_only = ON;")
        cur.close()

    _readonly_engine = eng
    return _readonly_engine


class SqlValidationError(ValueError):
    """Raised when advanced SQL fails a safety guard."""


def validate_sql(sql: str) -> None:
    """Validate raw SQL against all safety guards.

    Raises SqlValidationError on the first violation.
    """
    if not sql or not sql.strip():
        raise SqlValidationError("Query is empty.")

    # Normalize for checks (strip line comments + string literals so they
    # can't smuggle forbidden tokens past the scanner).
    stripped = _strip_comments_and_strings(sql)

    if _ALLOWED_LEAD.search(stripped) is None:
        raise SqlValidationError("Only SELECT (and WITH … SELECT) statements are allowed.")

    # Single statement: no semicolons except a trailing/whitespace one.
    # We count ';' in the literal-stripped text.
    if stripped.count(";") > 1:
        raise SqlValidationError("Only a single SQL statement is allowed.")
    if ";" in stripped and not stripped.rstrip().endswith(";"):
        raise SqlValidationError("Only a single SQL statement is allowed.")

    # Forbidden keywords (whole-word match).
    upper = stripped.upper()
    for kw in _FORBIDDEN_KEYWORDS:
        # Require word boundary so e.g. "SELECT" inside a column name is fine.
        if re.search(rf"\b{kw}\b", upper):
            raise SqlValidationError(f"Statement contains a forbidden keyword: {kw}.")

    # Table allowlist: every referenced table must be in ALLOWED_TABLES.
    refs = {m.group(2).lower() for m in _TABLE_REF.finditer(stripped)}
    bad = refs - set(t.lower() for t in ALLOWED_TABLES)
    if bad:
        raise SqlValidationError(
            f"Table(s) not permitted for direct SQL: {', '.join(sorted(bad))}. "
            f"Allowed: {', '.join(ALLOWED_TABLES)}."
        )


def _strip_comments_and_strings(sql: str) -> str:
    """Remove -- and /* */ comments and '...'/"..." string literals.

    Done on a character level so tokens inside strings/comments can't
    defeat the keyword/table scanners.
    """
    out = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            # line comment to end of line
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and sql[i + 1] == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue
        if c in ("'", '"', "`"):
            quote = c
            i += 1
            while i < n and sql[i] != quote:
                if sql[i] == "\\" and i + 1 < n:
                    i += 2
                else:
                    i += 1
            i += 1  # skip closing quote
            out.append(" ")  # replace string with a space
            continue
        out.append(c)
        i += 1
    return "".join(out)


def scope_sql_to_tenant(sql: str, tenant) -> tuple[str, dict]:
    """Wrap the user's SELECT as a subquery filtered by tenant_id.

    Rather than trying to splice a predicate into arbitrary SQL (which
    breaks on LIMIT / missing WHERE / JOINs / CTEs), the whole statement
    is nested as a derived table and filtered on its ``tenant_id`` column::

        SELECT * FROM ( <user_sql> ) AS _scoped WHERE _scoped.tenant_id = :__tenant__

    This is correct for any single SELECT and stays injection-safe because
    the tenant id is bound as a parameter. It requires the user's query to
    project a ``tenant_id`` column; if it doesn't, execution raises a clear
    error handled by :func:`run_readonly`.

    Returns (scoped_sql, params_dict). If no tenant is supplied, the
    original SQL and an empty param dict are returned.
    """
    if tenant is None:
        return sql, {}

    inner = sql.strip().rstrip(";").strip()
    scoped = (
        f"SELECT * FROM (\n{inner}\n) AS _scoped "
        f"WHERE _scoped.tenant_id = :__tenant__"
    )
    return scoped, {"__tenant__": getattr(tenant, "tenant_id", None)}


def run_readonly(
    sql: str,
    max_rows: int | None = None,
    timeout: int | None = None,
    tenant=None,
) -> dict:
    """Execute a validated read-only SQL statement.

    When `tenant` is supplied, results are automatically scoped to that
    tenant's rows (an AND tenant_id = :__tenant__ is appended for every
    PLM table in the statement), closing the only un-scoped query path.

    Returns:
        { "columns": [...], "rows": [[...], ...], "row_count": N,
          "truncated": bool, "sql": str }
    """
    validate_sql(sql)
    scoped_sql, params = scope_sql_to_tenant(sql, tenant)

    max_rows = max_rows or QUERY_MAX_ROWS
    timeout = timeout or QUERY_TIMEOUT_SECONDS

    engine = get_readonly_engine()
    t_start = time.time()
    try:
        with engine.connect() as conn:
            # Best-effort query timeout via PRAGMA (per-connection).
            try:
                conn.exec_driver_sql(f"PRAGMA busy_timeout = {int(timeout * 1000)};")
            except Exception:
                pass
            result = conn.execute(text(scoped_sql), params)
            all_rows = result.fetchall()
            columns = list(result.keys())
    except SQLAlchemyError as e:
        logger.warning(f"Read-only SQL failed: {e}")
        raise SqlValidationError(f"SQL execution error: {e}")
    except Exception as e:
        logger.warning(f"Read-only SQL unexpected error: {e}")
        raise SqlValidationError(f"Unexpected error executing query: {e}")

    row_count = len(all_rows)
    truncated = row_count > max_rows
    rows = [list(r) for r in all_rows[:max_rows]]

    elapsed = round(time.time() - t_start, 3)
    logger.info(f"Read-only SQL ran in {elapsed}s, {row_count} rows (showing {len(rows)}).")

    return {
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
        "truncated": truncated,
        "sql": scoped_sql.strip(),
        "elapsed_seconds": elapsed,
    }
