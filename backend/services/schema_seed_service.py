"""Schema/seed deployment service - replicates database/deploy-schema.bat as a background job.

Why this service exists
-----------------------
Schema and seed deployment were previously only available via the Windows batch
script ``database\\deploy-schema.bat``, which requires Docker Desktop and a
shell. This service brings the same capability into the running application so
operators can trigger schema/seed changes from the Developer UI without leaving
the browser.

Design
------
* Composes the existing ``JobRegistry`` for background execution and ``db`` for
  admin-level SQL execution (no tenant RLS).
* ``delta`` mode applies only files not yet recorded in
  ``plmiqdb.foundation_schema_migrations`` (idempotent, safe to re-run).
* ``fresh`` mode drops schema ``plmiqdb`` CASCADE before applying, so every
  file replays from scratch.
* File execution order is lexical (same as the batch script's ``for %%f``
  glob).

Logging contract
----------------
Every run writes ``<repo>/logs/<UTC stamp>_schema_seed.log``: one line per
file outcome and a final summary. The Developer UI surfaces the latest log
tail so operators can audit a run without leaving the browser.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from datetime import datetime as dt
from datetime import timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from . import db
from .errors import ValidationFailed
from .jobs import JobRegistry, registry

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _REPO_ROOT / "database" / "schema"
_SEED_DIR = _REPO_ROOT / "database" / "seed"
_LOG_DIR = _REPO_ROOT / "logs"
_FRESH_HELPER = _REPO_ROOT / "backend" / "scripts" / "apply_schema_seed.py"


def _split_sql(content: str) -> list[str]:
    """Split SQL content into statements, respecting SQL syntax.

    A semicolon only terminates a statement when it is not inside:
      * PostgreSQL dollar-quoted bodies (``$$ ... $$`` / ``$tag$ ... $tag$``),
      * single-quoted string literals (``''`` escapes),
      * ``--`` line comments (which are dropped from the output).
    """
    statements: list[str] = []
    current: list[str] = []
    in_dollar = False
    dollar_tag = ""
    in_squote = False
    i = 0
    n = len(content)

    while i < n:
        ch = content[i]

        if in_dollar:
            if ch == "$":
                j = i + 1
                while j < n and content[j] != "$":
                    j += 1
                if j < n and content[i + 1 : j] == dollar_tag:
                    current.append(content[i : j + 1])
                    i = j + 1
                    in_dollar = False
                    dollar_tag = ""
                    continue
            current.append(ch)
            i += 1
            continue

        if in_squote:
            if ch == "'":
                if i + 1 < n and content[i + 1] == "'":
                    current.append("''")
                    i += 2
                    continue
                in_squote = False
            current.append(ch)
            i += 1
            continue

        if ch == "$":
            j = i + 1
            while j < n and content[j] != "$":
                j += 1
            if j < n:
                tag = content[i + 1 : j]
                current.append(content[i : j + 1])
                i = j + 1
                in_dollar = True
                dollar_tag = tag
                continue
        if ch == "-" and i + 1 < n and content[i + 1] == "-":
            while i < n and content[i] != "\n":
                i += 1
            continue
        if ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        if ch == "'":
            in_squote = True
            current.append(ch)
            i += 1
            continue

        current.append(ch)
        i += 1

    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


class SchemaSeedService:
    """Schema/seed deployment running on the shared JobRegistry."""

    def __init__(self, jobs: JobRegistry = registry) -> None:
        self.jobs = jobs

    def start(self, mode: str, actions: list[str], *, actor: str) -> str:
        """Validate inputs and launch the background deployment job.

        Returns the job id immediately; progress lives in the JobRegistry.

        ``delta`` mode runs in-process on a daemon thread. ``fresh`` mode
        spawns a detached helper process that stops this gateway first (the
        schema drop invalidates every live connection), applies schema/seed,
        then restarts the gateway - so the in-process job only records the
        handoff and the real work happens in the helper's own log file.
        """
        mode = (mode or "").strip().lower()
        if mode not in ("delta", "fresh"):
            raise ValidationFailed(f"invalid mode '{mode}' (expected delta or fresh)")
        if not actions:
            raise ValidationFailed("no actions selected")

        name = f"schema-seed:{mode}:{','.join(actions)}"
        active = self.jobs.find_active("schema-seed:")
        if active is not None:
            raise ValidationFailed(
                f"a schema/seed job is already {active['status']} (job {active['id']})"
            )

        if mode == "fresh":
            return self._start_fresh(actions)

        def target() -> dict[str, Any]:
            return self.run(mode, actions, actor=actor)

        return self.jobs.start_job(name, target)

    def _start_fresh(self, actions: list[str]) -> str:
        """Kill the gateway, apply schema/seed, restart - via a detached helper.

        The helper is spawned before any schema change so the server is already
        down when ``DROP SCHEMA ... CASCADE`` runs. Returns a handoff job id.
        """
        run_log = self._open_run_log()
        run_log.warning(
            "schema_seed.fresh.handoff: stopping gateway pid=%d then applying %s",
            os.getpid(),
            ",".join(actions),
        )
        self._close_run_log(run_log)

        cmd = [sys.executable, str(_FRESH_HELPER), str(os.getpid()), "fresh", ",".join(actions)]
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(
                cmd,
                cwd=str(_REPO_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creationflags,
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            run_log = self._open_run_log()
            run_log.error("schema_seed.fresh.spawn.failed: %s", exc)
            self._close_run_log(run_log)
            raise ValidationFailed(f"could not spawn fresh deploy helper: {exc}") from exc

        def target() -> dict[str, Any]:
            return {
                "mode": "fresh",
                "actions": actions,
                "status": "done",
                "note": "fresh deploy handed off to detached process; gateway is restarting",
            }

        return self.jobs.start_job("schema-seed:fresh", target)

    def run(self, mode: str, actions: list[str], *, actor: str) -> dict[str, Any]:
        """Synchronous core: drop (fresh), apply files, report."""
        run_log = self._open_run_log()
        started = dt.now(timezone.utc)
        report: dict[str, Any] = {
            "mode": mode,
            "actions": actions,
            "actor": actor,
            "started_at": started.isoformat(),
            "finished_at": None,
            "applied": [],
            "skipped": [],
            "errors": [],
            "status": "done",
        }

        try:
            if mode == "fresh":
                self._fresh_drop(run_log)

            self._ensure_bookkeeping()

            if "schema" in actions:
                self._apply_dir(_SCHEMA_DIR, mode, run_log, report)

            if "seed" in actions:
                if "schema" not in actions:
                    self._apply_dir(_SCHEMA_DIR, "delta", run_log, report)
                self._apply_dir(_SEED_DIR, mode, run_log, report)

            run_log.info(
                "schema_seed.summary applied=%d skipped=%d errors=%d",
                len(report["applied"]),
                len(report["skipped"]),
                len(report["errors"]),
            )
        except Exception as exc:
            report["status"] = "failed"
            report["error"] = f"{type(exc).__name__}: {exc}"
            run_log.error("schema_seed.failed: %s", exc, exc_info=True)
        finally:
            report["finished_at"] = dt.now(timezone.utc).isoformat()
            self._close_run_log(run_log)

        return report

    def recent_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        runs = [j for j in self.jobs.list_jobs() if j["name"].startswith("schema-seed:")]
        return runs[:limit]

    @staticmethod
    def latest_log_tail(lines: int = 200) -> str | None:
        logs = sorted(_LOG_DIR.glob("*_schema_seed.log"), reverse=True)
        if not logs:
            return None
        try:
            text = logs[0].read_text(encoding="utf-8")
            return "\n".join(text.splitlines()[-lines:])
        except Exception:
            return None

    # ── internals ──────────────────────────────────────────────────────────────

    def _apply_dir(
        self, directory: Path, mode: str, run_log: logging.Logger, report: dict[str, Any]
    ) -> None:
        sql_files = sorted(directory.glob("*.sql"))
        if not sql_files:
            run_log.info("schema_seed.no_files: %s", directory)
            return

        for path in sql_files:
            filename = path.name
            if mode == "delta" and self._is_applied(filename):
                run_log.info("schema_seed.skip: %s", filename)
                report["skipped"].append(filename)
                continue

            run_log.info("schema_seed.apply: %s", filename)
            try:
                self._execute_sql_file(path)
                self._record_applied(filename)
                report["applied"].append(filename)
                run_log.info("schema_seed.applied: %s", filename)
            except Exception as exc:
                error_msg = f"{type(exc).__name__}: {exc}"
                report["errors"].append({"file": filename, "error": error_msg})
                run_log.error("schema_seed.error: %s: %s", filename, error_msg)
                raise

    def _fresh_drop(self, run_log: logging.Logger) -> None:
        run_log.info("schema_seed.fresh.drop: dropping schema plmiqdb")
        with db.admin_session() as session:
            session.execute(text("DROP SCHEMA IF EXISTS plmiqdb CASCADE"))
        run_log.info("schema_seed.fresh.dropped")

    def _ensure_bookkeeping(self) -> None:
        """Prepare schema + migration bookkeeping, mirroring deploy-schema.bat."""
        with db.admin_session() as session:
            session.execute(text("CREATE SCHEMA IF NOT EXISTS plmiqdb"))
            session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS plmiqdb.foundation_schema_migrations ("
                    "filename text PRIMARY KEY, "
                    "applied_on timestamptz NOT NULL DEFAULT now())"
                )
            )

    def _execute_sql_file(self, path: Path) -> None:
        content = path.read_text(encoding="utf-8")
        statements = _split_sql(content)
        with db.admin_session() as session:
            for stmt in statements:
                stmt = stmt.strip()
                if not stmt:
                    continue
                if stmt.upper() in ("BEGIN", "COMMIT", "ROLLBACK"):
                    continue
                session.execute(text(stmt))

    def _is_applied(self, filename: str) -> bool:
        try:
            with db.admin_session() as session:
                row = session.execute(
                    text(
                        "SELECT count(*) FROM plmiqdb.foundation_schema_migrations "
                        "WHERE filename = :f"
                    ),
                    {"f": filename},
                ).scalar()
                return bool(row)
        except (OperationalError, ProgrammingError):
            return False

    def _record_applied(self, filename: str) -> None:
        with db.admin_session() as session:
            session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS plmiqdb.foundation_schema_migrations ("
                    "filename text PRIMARY KEY, "
                    "applied_on timestamptz NOT NULL DEFAULT now())"
                )
            )
            session.execute(
                text(
                    "INSERT INTO plmiqdb.foundation_schema_migrations (filename) "
                    "VALUES (:f) ON CONFLICT (filename) DO NOTHING"
                ),
                {"f": filename},
            )

    # ── per-run file logger ────────────────────────────────────────────────────

    def _open_run_log(self) -> logging.Logger:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = dt.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_logger = logging.getLogger(f"plmiq.schema_seed.{stamp}.{threading.get_ident()}")
        handler = logging.FileHandler(_LOG_DIR / f"{stamp}_schema_seed.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        run_logger.addHandler(handler)
        run_logger.setLevel(logging.INFO)
        run_logger.propagate = False
        return run_logger

    @staticmethod
    def _close_run_log(run_logger: logging.Logger) -> None:
        for handler in list(run_logger.handlers):
            handler.flush()
            handler.close()
            run_logger.removeHandler(handler)


schema_deploy = SchemaSeedService()
