"""DocumentService - the reference TSE subtype, as a class.

Why this class exists
---------------------
Inherits EVERYTHING vertex-shaped (CRUD, numbering, revisions, lifecycle,
optimistic locking, listing) from ``VertexCoreService`` and adds exactly the
two things that make a document a document:

1. The TSE extension row (``foundation_document`` file_* attributes). The
   base class handles the joined reads automatically via
   ``extension_table``/``ext_columns``; writes are orchestrated here because
   storage must run before inserts and cleanup must run on any failure.
2. File lifecycle management - attach/detach/download through the pluggable
   ``files`` StorageBackend, keeping metadata and bytes in lockstep and
   enforcing released-document immutability.

Benefits of the class model here
--------------------------------
* Reads need ZERO code: pinning ``extension_table`` + ``ext_columns`` gives
  LEFT-JOIN-with-defaults semantics for find/get/list from the base.
* ``self.kind`` scoping is inherited, so numbering pools can never cross
  into Part/EC sequences.
* Future document features (folder trees, effectivity, approval workflow)
  land as new methods on this class without touching the core.

How to extend (future scenarios)
--------------------------------
* New subtype capability -> add a method here that composes inherited core
  operations (``self.get`` / ``self.update``) with its own extension-row SQL.
* New subtype entirely -> subclass VertexCoreService like this one; do NOT
  add document-specific branches anywhere in the core.
"""
from __future__ import annotations

import logging
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import enums, tables
from .errors import Conflict, NotFound
from .file_store import files
from .schemas import DocumentCreate, DocumentOut, Page, VertexUpdate
from .vertex_service import VertexCoreService

logger = logging.getLogger(__name__)

_EXT = tables.foundation_document


class DocumentService(VertexCoreService):
    kind = enums.VertexKind.DOCUMENT
    out_model = DocumentOut
    create_model = DocumentCreate
    update_model = VertexUpdate
    extension_table = _EXT
    ext_columns = (
        func.coalesce(_EXT.c.file_is_directory, False).label("file_is_directory"),
        func.coalesce(_EXT.c.file_name, "").label("file_name"),
        _EXT.c.file_parent_id.label("file_parent_id"),
        func.coalesce(_EXT.c.file_full_path, "").label("file_full_path"),
        func.coalesce(_EXT.c.file_size_bytes, 0).label("file_size_bytes"),
        func.coalesce(_EXT.c.file_mime_type, "").label("file_mime_type"),
        func.coalesce(_EXT.c.file_checksum_sha256, "").label("file_checksum_sha256"),
        func.coalesce(_EXT.c.storage_key, "").label("storage_key"),
    )

    def __init__(self):
        super().__init__()
        self.sortable.update({
            "file_name": func.coalesce(_EXT.c.file_name, ""),
            "size": func.coalesce(_EXT.c.file_size_bytes, 0),
        })

    # ── create: two phases, one transaction ──────────────────────────────────

    def create(
        self,
        session: Session,
        tenant_id: UUID,
        data: DocumentCreate,
        actor: str,
        *,
        upload: tuple[str, str | None, BinaryIO] | None = None,
    ) -> DocumentOut:
        """Create the core row + extension row (+ optional stored file).

        ``upload`` is ``(filename, content_type, stream)``. Storage runs
        BEFORE any INSERT so an invalid upload never touches the database;
        if the database rejects either phase afterwards, the just-stored
        object is deleted again while the transaction rolls itself back.
        """
        stored = None
        try:
            if upload is not None:
                filename, content_type, stream = upload
                stored = files.save(tenant_id, filename, content_type, stream)

            created = super().create(session, tenant_id, data, actor=actor)

            # Always materialize an extension row: uniform rows keep the
            # v_document view total and reporting free of OUTER JOINs. All
            # columns have DEFAULTs, so metadata-only documents are legal.
            session.execute(insert(_EXT).values(
                id=created.id,
                tenant_id=tenant_id,
                file_is_directory=False,
                file_name=stored.name if stored else "",
                file_full_path=stored.name if stored else "",
                file_size_bytes=stored.size_bytes if stored else 0,
                file_mime_type=stored.mime_type if stored else "",
                file_checksum_sha256=stored.checksum_sha256 if stored else "",
                storage_key=stored.key if stored else "",
            ))
            logger.info("document.created", extra={
                "tenant": str(tenant_id), "vertex": str(created.id),
                "number": f"{data.prefix}-{data.number}", "actor": actor,
                "with_file": bool(stored),
            })
            return self._to_out(self.get(session, tenant_id, created.id))
        except Exception:
            if stored is not None:
                files.delete(tenant_id, stored.key)
            raise

    # ── file lifecycle ───────────────────────────────────────────────────────

    def attach_file(
        self,
        session: Session,
        tenant_id: UUID,
        vertex_id: UUID,
        actor: str,
        *,
        filename: str,
        content_type: str | None,
        stream: BinaryIO,
        expected_version: int,
    ) -> tuple[DocumentOut, str]:
        """Upload-or-replace content; returns (doc, PREVIOUS storage key).

        Callers delete the previous key only AFTER their transaction commits,
        so a rollback can never dangle the old pointer. The version bump goes
        through the inherited core path: two racing uploads lose deterministically.
        """
        current = self.get(session, tenant_id, vertex_id)
        self._ensure_mutable(current)
        stored = files.save(tenant_id, filename, content_type, stream)
        old_key = current["storage_key"]

        session.execute(
            pg_insert(_EXT)
            .values(
                id=vertex_id,
                tenant_id=tenant_id,
                file_is_directory=False,
                file_name=stored.name,
                file_full_path=stored.name,
                file_size_bytes=stored.size_bytes,
                file_mime_type=stored.mime_type,
                file_checksum_sha256=stored.checksum_sha256,
                storage_key=stored.key,
            )
            .on_conflict_do_update(
                index_elements=[_EXT.c.id],
                set_={
                    "file_is_directory": False,
                    "file_name": stored.name,
                    "file_full_path": stored.name,
                    "file_size_bytes": stored.size_bytes,
                    "file_mime_type": stored.mime_type,
                    "file_checksum_sha256": stored.checksum_sha256,
                    "storage_key": stored.key,
                },
            )
        )
        self.consume_version(session, tenant_id, vertex_id, actor=actor,
                             expected_version=expected_version)
        logger.info("document.file.attached", extra={
            "tenant": str(tenant_id), "vertex": str(vertex_id), "key": stored.key, "actor": actor,
        })
        return self._to_out(self.get(session, tenant_id, vertex_id)), old_key

    def detach_file(
        self,
        session: Session,
        tenant_id: UUID,
        vertex_id: UUID,
        actor: str,
        *,
        expected_version: int,
    ) -> tuple[DocumentOut, str]:
        """Clear content but keep the document (metadata-only state)."""
        current = self.get(session, tenant_id, vertex_id)
        self._ensure_mutable(current)
        if not current["storage_key"]:
            raise NotFound(
                f"document {current['prefix']}-{current['number']}/"
                f"{current['revision']} has no attached file"
            )
        old_key = current["storage_key"]
        session.execute(update(_EXT).where(_EXT.c.id == vertex_id).values(
            file_name="", file_full_path="", file_size_bytes=0,
            file_mime_type="", file_checksum_sha256="", storage_key="",
        ))
        self.consume_version(session, tenant_id, vertex_id, actor=actor,
                             expected_version=expected_version)
        logger.info("document.file.detached", extra={
            "tenant": str(tenant_id), "vertex": str(vertex_id), "actor": actor,
        })
        return self._to_out(self.get(session, tenant_id, vertex_id)), old_key

    def download(self, session: Session, tenant_id: UUID, vertex_id: UUID):
        """Resolve stored content for streaming: (stream, filename, mime, size)."""
        current = self.get(session, tenant_id, vertex_id)
        if not current["storage_key"]:
            raise NotFound(
                f"document {current['prefix']}-{current['number']}/"
                f"{current['revision']} has no attached file"
            )
        stream, _ = files.open_stream(tenant_id, current["storage_key"])
        logger.info("document.file.downloaded", extra={
            "tenant": str(tenant_id), "vertex": str(vertex_id), "key": current["storage_key"],
        })
        filename = current["file_name"] or f"{current['prefix']}-{current['number']}"
        return stream, filename, current["file_mime_type"] or "application/octet-stream", \
            current["file_size_bytes"]

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_mutable(current: dict) -> None:
        if current["lifecycle_state"] == enums.LifecycleState.RELEASED:
            raise Conflict(
                f"document {current['prefix']}-{current['number']} is Released; "
                "its file can only change via a new revision or the change process"
            )

    def consume_version(self, session: Session, tenant_id: UUID, vertex_id: UUID, *,
                        actor: str, expected_version: int) -> None:
        """Empty-change versioned UPDATE: stamps audit columns and fires the
        core bump_version trigger, consuming one optimistic-lock token."""
        self._versioned_update(
            session,
            tables.foundation_vertex,
            {},
            row_id=vertex_id,
            tenant_id=tenant_id,
            expected_version=expected_version,
            actor=actor,
        )


#: Pinned singleton used by the gateway; kind-scoped to Documents.
documents = DocumentService()
