"""BulkFileUploadService - folder-driven bulk creation of Documents + files.

Why this service exists
-----------------------
Onboarding real data means ingesting whole folders of drawings, specs and
PDFs in one action. Doing it file-by-file through the UI does not scale, so
this service scans a server-side folder and creates one Document per file
(shared-core vertex + TSE extension row + stored bytes) as a BACKGROUND job,
then produces a report of exactly what was created.

Design (OOP, built to extend)
-----------------------------
* Composes existing singletons instead of reimplementing them:
  ``documents`` (core CRUD + numbering), ``files`` (StorageBackend),
  ``registry`` (background jobs). Nothing here touches SQL or paths directly
  except the folder being imported.
* Extensible by override, not by editing loops:
  - ``should_import(path)``        -> filter which files qualify
  - ``document_for(path, number)`` -> control the payload per file (e.g.
    parse a CSV sidecar for metadata, route by extension)
  - ``prefix``/``revision``        -> defaults for generated numbers
  Future scenarios land as subclasses (ZipArchiveImporter unpacking first,
  CsvManifestImporter reading metadata) without touching the gateway.

Logging contract
----------------
Every run writes ``<repo>/logs/<UTC stamp>_bulk_file_upload.log`` (plus the
normal console log): one line per file outcome and a final summary, so an
operator can audit a run even after the in-memory job record is pruned.

How to use
----------
    from services.bulk_file_upload_service import bulk_uploads
    job_id = bulk_uploads.start(Path(r"C:\\data\\drawings"), actor=...)
    # poll registry.get_job(job_id); when status == "done", job["result"]
    # holds the report dict consumed by the admin UI.
"""
from __future__ import annotations

import logging
import mimetypes
import threading
from datetime import datetime as dt, timezone
from pathlib import Path
from typing import Any

from . import db
from .document_service import documents
from .enums import EditionId, VertexKind
from .errors import ValidationFailed
from .file_store import files
from .jobs import JobRegistry, registry
from .schemas import DocumentCreate

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = _REPO_ROOT / "logs"

_DEFAULT_PREFIX = "DOC"
_DEFAULT_REVISION = "A"


class BulkFileUploadService:
    """Folder -> Documents pipeline running on the shared JobRegistry."""

    def __init__(self, documents_service=documents, storage: Any = files,
                 jobs: JobRegistry = registry):
        self.documents = documents_service
        self.files = storage
        self.jobs = jobs

    # ── public API ───────────────────────────────────────────────────────────

    def start(self, folder: str | Path, *, tenant_id: Any, edition_id: EditionId,
              actor: str, prefix: str = _DEFAULT_PREFIX) -> str:
        """Validate the folder and launch the background import.

        Returns the job id immediately; progress lives in the JobRegistry and
        the finished report in ``self.report(job_id)`` / the job's result.
        """
        path = Path((folder or "").strip())
        if not path.is_dir():
            raise ValidationFailed(f"folder '{folder}' does not exist on the server")
        name = f"bulk-upload:{path.name}"
        active = self.jobs.find_active("bulk-upload:")
        if active is not None:
            raise ValidationFailed(
                f"a bulk upload is already {active['status']} (job {active['id']})"
            )

        def target() -> dict:
            return self.run(path, tenant_id=tenant_id, edition_id=edition_id,
                            actor=actor, prefix=prefix)

        return self.jobs.start_job(name, target)

    def report(self, job_id: str) -> dict | None:
        """Report for a finished run - read straight from the job's result."""
        record = self.jobs.get_job(job_id)
        if record and record.get("result"):
            return dict(record["result"])
        return None

    def recent_jobs(self, limit: int = 10) -> list[dict]:
        runs = [j for j in self.jobs.list_jobs() if j["name"].startswith("bulk-upload:")]
        return runs[:limit]

    # ── the pipeline ─────────────────────────────────────────────────────────

    def run(self, folder: Path, *, tenant_id: Any, edition_id: EditionId,
            actor: str, prefix: str = _DEFAULT_PREFIX) -> dict:
        """Synchronous core: scan, create, store, report. Thread-safe."""
        run_log = self._open_run_log()
        started = dt.now(timezone.utc)
        files_found = sorted(
            p for p in Path(folder).iterdir() if p.is_file() and self.should_import(p)
        )
        items: list[dict] = []
        run_log.info("bulk.run.started", extra={
            "folder": str(folder), "files": len(files_found), "actor": actor,
        })

        for path in files_found:
            entry: dict[str, Any] = {"file": path.name, "status": "failed",
                                     "document": None, "error": None}
            try:
                with db.tenant_session(tenant_id) as session:
                    number = self.documents.next_number(session, tenant_id, prefix=prefix)
                    data = self.document_for(path, number, edition_id, prefix=prefix)
                    created = self.documents.create(
                        session, tenant_id, data, actor=actor,
                        upload=self.upload_for(path),
                    )
                entry.update(status="created",
                             document=f"{created.prefix}-{created.number}/{created.revision}",
                             document_id=str(created.id))
            except Exception as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
                run_log.error("bulk.file.failed %s %s", path.name, entry["error"])
            items.append(entry)
            if entry["status"] == "created":
                run_log.info("bulk.file.created %s -> %s", path.name, entry["document"])

        created_count = sum(1 for i in items if i["status"] == "created")
        report = {
            "folder": str(folder),
            "started_at": started.isoformat(),
            "finished_at": dt.now(timezone.utc).isoformat(),
            "total": len(items),
            "created": created_count,
            "failed": len(items) - created_count,
            "entries": items,
        }
        run_log.info("bulk.run.summary created=%d failed=%d total=%d",
                     created_count, len(items) - created_count, len(items))
        self._close_run_log(run_log)
        return report

    # ── override points for future upload kinds ──────────────────────────────

    def should_import(self, path: Path) -> bool:
        """Filter rule; subclasses may skip e.g. hidden files or sidecars."""
        return not path.name.startswith(".")

    def document_for(self, path: Path, number: str, edition_id: EditionId,
                     prefix: str = _DEFAULT_PREFIX) -> DocumentCreate:
        """Payload policy: generated number, filename as Name, revision A."""
        return DocumentCreate(
            edition_id=edition_id,
            kind=VertexKind.DOCUMENT,   # explicit: base create dumps full model
            prefix=prefix or _DEFAULT_PREFIX,
            number=number,
            name=path.stem or path.name,
            revision=_DEFAULT_REVISION,
        )

    def upload_for(self, path: Path) -> tuple[str, str | None, Any]:
        mime, _ = mimetypes.guess_type(path.name)
        return path.name, mime, open(path, "rb")

    # ── per-run file logger ──────────────────────────────────────────────────

    @staticmethod
    def _open_run_log() -> logging.Logger:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = dt.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_logger = logging.getLogger(f"plmiq.bulk_upload.{stamp}.{threading.get_ident()}")
        handler = logging.FileHandler(LOG_DIR / f"{stamp}_bulk_file_upload.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        run_logger.addHandler(handler)
        run_logger.setLevel(logging.INFO)
        run_logger.propagate = False  # keep the run file authoritative on disk
        return run_logger

    @staticmethod
    def _close_run_log(run_logger: logging.Logger) -> None:
        for handler in list(run_logger.handlers):
            handler.flush()
            handler.close()
            run_logger.removeHandler(handler)


#: Shared singleton wired to the process-wide document/storage/job stack.
bulk_uploads = BulkFileUploadService()
