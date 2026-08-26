"""Tenant-partitioned object storage for uploaded files.

Why this is a separate service: a document's *business* identity (number,
name, revision, lifecycle) lives on the vertex; where its bytes live is an
infrastructure concern. Keeping save/open/delete behind this module means the
local directory can be swapped for S3/Azure Blob later without touching
document_service or any UI code (strategy Section 16: object storage holds
files).

Layout under ``PLMIQ_FILE_STORAGE_DIR`` (default ``<repo>/data/file-volume``)::

    {tenant_id}/documents/{uuid}-{sanitized-name}

- The tenant partition comes first, matching the isolation-mechanism table in
  strategy Section 4 (tenant-prefixed object keys): cross-tenant access would
  have to aim at a foreign path prefix, which the traversal guard rejects.
- A uuid prefixes every stored name because user-supplied names are neither
  unique nor safe; the sanitized original survives only for humans browsing
  the folder. Downloads always use the name recorded on the extension row.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid as uuid_mod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from .errors import NotFound, ValidationFailed

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_storage_root(raw: str) -> Path:
    """Resolve the storage root from an absolute or repo-relative path.

    Relative values resolve against the repository root rather than the
    process working directory, so one ``PLMIQ_FILE_STORAGE_DIR=data/file-volume``
    line behaves identically however and wherever the gateway is started.
    """
    path = Path(raw)
    return path if path.is_absolute() else (_REPO_ROOT / path).resolve()


STORAGE_ROOT = _resolve_storage_root(
    os.getenv("PLMIQ_FILE_STORAGE_DIR", str(_REPO_ROOT / "data" / "file-volume"))
)

MAX_UPLOAD_BYTES = int(os.getenv("PLMIQ_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))

_READ_CHUNK = 1024 * 1024

_MAX_NAME_LENGTH = 120

_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9 ._()-]+")


@dataclass(frozen=True)
class StoredFile:
    """Metadata of one successfully stored upload."""

    key: str  # tenant-relative storage key persisted on the extension row
    name: str  # sanitized display name (with extension)
    size_bytes: int
    mime_type: str
    checksum_sha256: str


def safe_name(raw: str) -> str:
    """Sanitize a client-supplied filename.

    Browsers send anything from ``report.pdf`` to ``../../etc/passwd`` or
    empty strings. We strip path components and control characters, cap the
    length while preserving the extension, and fall back to a neutral name -
    the storage key never depends on this value being pretty.
    """
    name = os.path.basename((raw or "").replace("\\", "/")).strip()
    cleaned = _UNSAFE_NAME_CHARS.sub("_", name).strip(". ")
    if not cleaned:
        return "file.bin"
    if len(cleaned) > _MAX_NAME_LENGTH:
        stem, dot, suffix = cleaned.rpartition(".")
        keep = _MAX_NAME_LENGTH - len(dot + suffix) - 1
        cleaned = (stem[:max(keep, 1)] + "~" + dot + suffix) if dot else cleaned[:_MAX_NAME_LENGTH]
    return cleaned


def safe_mime(content_type: str | None) -> str:
    """Normalize the browser-declared media type.

    The header is advisory only (clients can lie), so we accept plain
    ``type/subtype`` values and default everything else rather than trusting
    arbitrary strings into the database.
    """
    candidate = (content_type or "").split(";")[0].strip().lower()
    if re.fullmatch(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+", candidate):
        return candidate
    return "application/octet-stream"


def _tenant_dir(tenant_id: UUID) -> Path:
    return STORAGE_ROOT / str(tenant_id)


def _resolve_key(tenant_id: UUID, key: str) -> Path:
    """Resolve a stored key to a path inside the tenant partition.

    Every read/delete passes through this guard: keys containing ``..`` or
    absolute components resolve outside the tenant directory and are rejected
    before touching the filesystem.
    """
    root = _tenant_dir(tenant_id).resolve()
    target = (root / key).resolve()
    if not target.is_relative_to(root):
        raise ValidationFailed("invalid storage key")
    return target


def save(tenant_id: UUID, filename: str, content_type: str | None, stream: BinaryIO) -> StoredFile:
    """Stream an upload into the tenant partition, hashing as it goes.

    Size is enforced mid-stream (not after): a 10 GB body must fail at the
    50 MB mark instead of materializing on disk first. On any rejection or IO
    error the partial file is removed so failed uploads leave no debris.
    """
    display = safe_name(filename)
    key = f"documents/{uuid_mod.uuid4().hex}-{display}"
    target = _resolve_key(tenant_id, key)
    target.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("wb") as sink:
            while chunk := stream.read(_READ_CHUNK):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValidationFailed(
                        f"file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit"
                    )
                digest.update(chunk)
                sink.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        logger.warning(
            "file.store.rejected",
            extra={"tenant": str(tenant_id), "name": display, "size": size},
        )
        raise

    stored = StoredFile(
        key=key,
        name=display,
        size_bytes=size,
        mime_type=safe_mime(content_type),
        checksum_sha256=digest.hexdigest(),
    )
    logger.info(
        "file.store.saved",
        extra={
            "tenant": str(tenant_id),
            "key": key,
            "size": stored.size_bytes,
            "sha256": stored.checksum_sha256[:12],
        },
    )
    return stored


def open_stream(tenant_id: UUID, key: str, expected_size: int = 0) -> tuple[BinaryIO, int]:
    """Open a stored object for streaming download.

    Returns an open binary handle plus the byte size recorded at upload time;
    callers set Content-Length from it instead of stat-ing again. A missing
    object is a NotFound with context rather than a raw OSError, so the UI
    can flash a meaningful message for dangling metadata.
    """
    if not key:
        raise ValidationFailed("document has no attached file")
    target = _resolve_key(tenant_id, key)
    if not target.is_file():
        logger.warning("file.store.missing", extra={"tenant": str(tenant_id), "key": key})
        raise NotFound("stored file content is missing; re-upload the document file")
    return target.open("rb"), expected_size


def delete(tenant_id: UUID, key: str) -> None:
    """Remove a stored object; best-effort by design.

    Orphaned bytes on disk are harmless garbage a cleanup sweep can collect;
    raising here would block the database transaction that already removed
    the pointer, turning tidy-up into an outage risk. Failures are logged for
    operations instead.
    """
    if not key:
        return
    try:
        target = _resolve_key(tenant_id, key)
        target.unlink(missing_ok=True)
        # Prune now-empty directories up to (not including) the tenant root.
        parent = target.parent
        while parent != _tenant_dir(tenant_id).resolve() and parent.is_dir():
            parent.rmdir()
            parent = parent.parent
        logger.info("file.store.deleted", extra={"tenant": str(tenant_id), "key": key})
    except OSError as exc:
        logger.warning("file.store.delete_failed", extra={"tenant": str(tenant_id), "key": key, "error": str(exc)})
