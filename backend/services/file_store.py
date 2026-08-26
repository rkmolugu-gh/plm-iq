"""StorageBackend - pluggable, tenant-partitioned file storage.

Why this class hierarchy exists
-------------------------------
Documents describe *business* content (number, revision, lifecycle); where
their bytes live is an infrastructure concern. The ABC makes that seam
explicit: ``DocumentService`` depends on the ``StorageBackend`` interface,
never on the filesystem. Swapping to S3/Azure Blob later is a new subclass
plus one line at the bottom of this module - no changes to document_service
or any UI code (strategy Section 16: object storage holds files).

Benefits
--------
* Tenant partitioning + traversal guarding live in exactly one place.
* Tests inject a fake backend (in-memory dict) for deterministic runs.
* Checksum/size policy is enforced uniformly for every backend.

How to extend (future scenarios)
--------------------------------
::

    class S3Storage(StorageBackend):
        def save(self, tenant_id, filename, content_type, stream): ...
        def open_stream(self, tenant_id, key): ...
        def delete(self, tenant_id, key): ...

    files = S3Storage(bucket="plmiq-files")   # single swap point

Layout contract (LocalFileStorage), under PLMIQ_FILE_STORAGE_DIR
(default ``<repo>/data/file-volume``)::

    {tenant_id}/documents/{uuid}-{sanitized-name}

- Tenant partition first, mirroring strategy Section 4 isolation
  (tenant-prefixed object keys).
- A uuid prefixes every stored name: client names are neither unique nor
  safe; downloads use the name recorded on the document extension row.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid as uuid_mod
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from .errors import NotFound, ValidationFailed

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]

_READ_CHUNK = 1024 * 1024
_MAX_NAME_LENGTH = 120
_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9 ._()-]+")


def _resolve_storage_root(raw: str) -> Path:
    """Resolve absolute or repo-relative paths identically everywhere.

    Relative values resolve against the repository root rather than the
    process working directory, so one
    ``PLMIQ_FILE_STORAGE_DIR=data/file-volume`` line behaves identically
    however and wherever the gateway is started.
    """
    path = Path(raw)
    return path if path.is_absolute() else (_REPO_ROOT / path).resolve()


@dataclass(frozen=True)
class StoredFile:
    """Metadata of one successfully stored upload."""

    key: str  # tenant-relative storage key persisted on the extension row
    name: str  # sanitized display name (with extension)
    size_bytes: int
    mime_type: str
    checksum_sha256: str


class StorageBackend(ABC):
    """Interface every object store must satisfy. Keys are TENANT-RELATIVE."""

    @abstractmethod
    def save(self, tenant_id: UUID, filename: str, content_type: str | None,
             stream: BinaryIO) -> StoredFile:
        """Persist an upload stream; enforce size limits; return metadata."""

    @abstractmethod
    def open_stream(self, tenant_id: UUID, key: str) -> tuple[BinaryIO, int]:
        """Open a stored object; return (stream, recorded size)."""

    @abstractmethod
    def delete(self, tenant_id: UUID, key: str) -> None:
        """Best-effort removal; must never raise for missing keys."""


class LocalFileStorage(StorageBackend):
    """Filesystem implementation: one directory tree per tenant."""

    def __init__(self, root: str | Path | None = None, max_upload_bytes: int | None = None):
        self.root = _resolve_storage_root(
            str(root) if root else os.getenv(
                "PLMIQ_FILE_STORAGE_DIR", str(_REPO_ROOT / "data" / "file-volume")
            )
        )
        self.max_upload_bytes = max_upload_bytes or int(
            os.getenv("PLMIQ_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))
        )

    # ── StorageBackend ───────────────────────────────────────────────────────

    def save(self, tenant_id: UUID, filename: str, content_type: str | None,
             stream: BinaryIO) -> StoredFile:
        display = self.safe_name(filename)
        key = f"documents/{uuid_mod.uuid4().hex}-{display}"
        target = self._resolve_key(tenant_id, key)
        target.parent.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        size = 0
        try:
            with target.open("wb") as sink:
                while chunk := stream.read(_READ_CHUNK):
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise ValidationFailed(
                            f"file exceeds the {self.max_upload_bytes // (1024 * 1024)} MB upload limit"
                        )
                    digest.update(chunk)
                    sink.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            logger.warning("file.store.rejected", extra={
                "tenant": str(tenant_id), "name": display, "size": size,
            })
            raise

        stored = StoredFile(
            key=key,
            name=display,
            size_bytes=size,
            mime_type=self.safe_mime(content_type),
            checksum_sha256=digest.hexdigest(),
        )
        logger.info("file.store.saved", extra={
            "tenant": str(tenant_id), "key": key, "size": stored.size_bytes,
            "sha256": stored.checksum_sha256[:12],
        })
        return stored

    def open_stream(self, tenant_id: UUID, key: str) -> tuple[BinaryIO, int]:
        if not key:
            raise ValidationFailed("document has no attached file")
        target = self._resolve_key(tenant_id, key)
        if not target.is_file():
            logger.warning("file.store.missing", extra={"tenant": str(tenant_id), "key": key})
            raise NotFound("stored file content is missing; re-upload the document file")
        return target.open("rb"), target.stat().st_size

    def delete(self, tenant_id: UUID, key: str) -> None:
        """Best-effort by design: orphaned bytes are harmless garbage a sweep
        can collect; raising here would risk DB rows pointing at deleted bytes."""
        if not key:
            return
        try:
            target = self._resolve_key(tenant_id, key)
            target.unlink(missing_ok=True)
            parent = target.parent
            tenant_root = (self.root / str(tenant_id)).resolve()
            while parent != tenant_root and parent.is_dir():
                if next(parent.iterdir(), None) is not None:
                    break  # still holds other objects; stop pruning here
                parent.rmdir()
                parent = parent.parent
            logger.info("file.store.deleted", extra={"tenant": str(tenant_id), "key": key})
        except OSError as exc:
            logger.warning("file.store.delete_failed", extra={
                "tenant": str(tenant_id), "key": key, "error": str(exc),
            })

    # ── helpers ──────────────────────────────────────────────────────────────

    def _tenant_dir(self, tenant_id: UUID) -> Path:
        return self.root / str(tenant_id)

    def _resolve_key(self, tenant_id: UUID, key: str) -> Path:
        """Resolve a stored key inside the tenant partition.

        Every read/delete passes through this guard: keys containing ``..`` or
        absolute components resolve outside the tenant directory and are
        rejected before touching the filesystem.
        """
        root = self._tenant_dir(tenant_id).resolve()
        target = (root / key).resolve()
        if not target.is_relative_to(root):
            raise ValidationFailed("invalid storage key")
        return target

    @staticmethod
    def safe_name(raw: str) -> str:
        """Sanitize a client-supplied filename (path parts, control chars)."""
        name = os.path.basename((raw or "").replace("\\", "/")).strip()
        cleaned = _UNSAFE_NAME_CHARS.sub("_", name).strip(". ")
        if not cleaned:
            return "file.bin"
        if len(cleaned) > _MAX_NAME_LENGTH:
            stem, dot, suffix = cleaned.rpartition(".")
            keep = _MAX_NAME_LENGTH - len(dot + suffix) - 1
            cleaned = (stem[:max(keep, 1)] + "~" + dot + suffix) if dot else cleaned[:_MAX_NAME_LENGTH]
        return cleaned

    @staticmethod
    def safe_mime(content_type: str | None) -> str:
        """Normalize the browser-declared media type (clients can lie)."""
        candidate = (content_type or "").split(";")[0].strip().lower()
        if re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", candidate):
            return candidate
        return "application/octet-stream"


#: Process-wide backend. Swap to another StorageBackend subclass here.
files = LocalFileStorage()
