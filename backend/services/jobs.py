"""JobRegistry - in-process background job runner for long-running tasks.

Why this class exists
---------------------
Indexing and Elasticsearch ingestion can take minutes, so the gateway hands
them to daemon threads and returns immediately. Job records live in memory
(they are progress reporting, not durable state); durable outcomes such as
the incremental-index watermark live in the owning services.

OOP rationale
-------------
The job table + lock used to be module globals - mutable state reachable
from anywhere, impossible to isolate in tests or swap out. Encapsulating
them in ``JobRegistry`` means:

Benefits
--------
* State and its locking discipline live together; no caller can bypass the lock.
* Tests inject their own ``JobRegistry()`` for deterministic assertions.
* A future Redis/DB-backed registry is a subclass swap at one call site
  (``registry = ...``) - callers keep calling the same methods.

How to extend (future scenarios)
--------------------------------
* Durable jobs -> subclass and override ``_records`` persistence.
* Cancellation/progress % -> add record fields + a cancel() method here.

Semantics kept EXACTLY as before: records are process-local by contract, so
behavior under multiple workers is unchanged (each worker reports only its
own jobs).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid as uuid_mod
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class JobRegistry:
    def __init__(self, *, max_retained: int = 100):
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._max_retained = max_retained

    def start_job(self, name: str, target: Callable[[], dict[str, Any]]) -> str:
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
        with self._lock:
            self._jobs[job_id] = record
            self._prune()

        def runner() -> None:
            with self._lock:
                record["status"] = "running"
                record["started_at"] = time.time()
            try:
                result = target()
            except Exception as exc:
                logger.exception("job.failed", extra={"job": job_id, "name": name})
                with self._lock:
                    record["status"] = "failed"
                    record["error"] = f"{type(exc).__name__}: {exc}"
            else:
                with self._lock:
                    record["status"] = "done"
                    record["result"] = result
            finally:
                with self._lock:
                    record["finished_at"] = time.time()

        threading.Thread(target=runner, name=f"plmiq-{name}-{job_id}", daemon=True).start()
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return dict(record) if record else None

    def list_jobs(self) -> list[dict[str, Any]]:
        """Snapshot of all retained jobs, newest first."""
        with self._lock:
            return [
                dict(self._jobs[job_id])
                for job_id in sorted(self._jobs, key=lambda j: self._jobs[j]["submitted_at"], reverse=True)
            ]

    def find_active(self, name_prefix: str) -> dict[str, Any] | None:
        with self._lock:
            for record in self._jobs.values():
                if record["name"].startswith(name_prefix) and record["status"] in ("queued", "running"):
                    return dict(record)
        return None

    def any_active(self) -> bool:
        with self._lock:
            return any(r["status"] in ("queued", "running") for r in self._jobs.values())

    def _prune(self) -> None:
        """Caller must hold the lock."""
        if len(self._jobs) <= self._max_retained:
            return
        finished = sorted(
            (r for r in self._jobs.values() if r["status"] in ("done", "failed")),
            key=lambda r: r["finished_at"] or 0,
        )
        for record in finished[: len(self._jobs) - self._max_retained]:
            self._jobs.pop(record["id"], None)


#: Process-local singleton (see class docstring for the multi-worker contract).
registry = JobRegistry()
