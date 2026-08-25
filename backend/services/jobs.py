"""In-process background job runner for long-running service tasks.

Indexing and Elasticsearch ingestion can take minutes, so the gateway hands
them to daemon threads and returns immediately. Job records live in memory
(they are progress reporting, not durable state); durable outcomes such as
the incremental-index watermark live in the owning services.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid as uuid_mod
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_MAX_RETAINED = 100


def start_job(name: str, target: Callable[[], dict[str, Any]]) -> str:
    """Run ``target`` on a daemon thread; return the job id immediately."""
    job_id = uuid_mod.uuid4().hex[:12]
    record: dict[str, Any] = {
        "id": job_id,
        "name": name,
        "status": "queued",
        "submitted_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }
    with _LOCK:
        _JOBS[job_id] = record
        _prune()

    def runner() -> None:
        with _LOCK:
            record["status"] = "running"
            record["started_at"] = time.time()
        try:
            result = target()
        except Exception as exc:
            logger.exception("job.failed", extra={"job": job_id, "name": name})
            with _LOCK:
                record["status"] = "failed"
                record["error"] = f"{type(exc).__name__}: {exc}"
        else:
            with _LOCK:
                record["status"] = "done"
                record["result"] = result
        finally:
            with _LOCK:
                record["finished_at"] = time.time()

    threading.Thread(target=runner, name=f"plmiq-{name}-{job_id}", daemon=True).start()
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        record = _JOBS.get(job_id)
        return dict(record) if record else None


def list_jobs() -> list[dict[str, Any]]:
    """Snapshot of all retained jobs, newest first."""
    with _LOCK:
        return [dict(_JOBS[job_id]) for job_id in sorted(_JOBS, key=lambda j: _JOBS[j]["submitted_at"], reverse=True)]


def find_active(name_prefix: str) -> dict[str, Any] | None:
    with _LOCK:
        for record in _JOBS.values():
            if record["name"].startswith(name_prefix) and record["status"] in ("queued", "running"):
                return dict(record)
    return None


def any_active() -> bool:
    with _LOCK:
        return any(r["status"] in ("queued", "running") for r in _JOBS.values())


def _prune() -> None:
    if len(_JOBS) <= _MAX_RETAINED:
        return
    finished = sorted(
        (r for r in _JOBS.values() if r["status"] in ("done", "failed")),
        key=lambda r: r["finished_at"] or 0,
    )
    for record in finished[: len(_JOBS) - _MAX_RETAINED]:
        _JOBS.pop(record["id"], None)
