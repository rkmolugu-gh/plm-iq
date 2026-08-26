"""Document management - the reference TSE subtype service.

Composition over the shared core (strategy Section 8, "Shared-Core Vertex
with Typed Subtype Extensions"): everything that makes a row a *vertex*
(numbering, uniqueness, revisions, lifecycle transitions, optimistic locking,
soft delete) is reused from ``vertex_service`` untouched. This module owns
exactly two things:

1. The extension row in ``foundation_document`` (file_* attributes). Writes
   are two-phase - core write, then extension write - inside ONE transaction,
   so a crash can never leave a vertex without its extension half. The
   extension row is created together with the vertex even when no file is
   attached yet: uniform rows keep the ``v_document`` view total, so SQL
   consumers never need OUTER JOINs to see their documents.
2. The file lifecycle. Bytes go through ``file_store``; this module keeps the
   extension-row metadata (name, size, mime, checksum, storage key) exactly
   in sync with what is actually stored, and enforces the released-document
   immutability rule for content swaps.

Deliberately NOT here: folder trees, effectivity, approval workflows - those
are future document features and will layer on without changing the core.
"""
from __future__ import annotations

import logging
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import enums, file_store, tables, vertex_service
from .errors import Conflict, NotFound
from .schemas import DocumentCreate, DocumentOut, Page, VertexUpdate, from_row

logger = logging.getLogger(__name__)

_EXT = tables.foundation_document
_CORE = tables.foundation_vertex

# Column pairs selected as one flat row - the in-code equivalent of v_document.
# Overlapping names (id, tenant_id) come only from the core side; extension
# columns are coalesced to their DEFAULTs because TSE treats a missing
# extension row as "subtype attributes at defaults" (strategy Section 8):
# seeded or imported documents must list and revise without one.
_CORE_COLS = [c for c in _CORE.c]
_EXT_COLS = [
    func.coalesce(_EXT.c.file_is_directory, False).label("file_is_directory"),
    func.coalesce(_EXT.c.file_name, "").label("file_name"),
    _EXT.c.file_parent_id.label("file_parent_id"),
    func.coalesce(_EXT.c.file_full_path, "").label("file_full_path"),
    func.coalesce(_EXT.c.file_size_bytes, 0).label("file_size_bytes"),
    func.coalesce(_EXT.c.file_mime_type, "").label("file_mime_type"),
    func.coalesce(_EXT.c.file_checksum_sha256, "").label("file_checksum_sha256"),
    func.coalesce(_EXT.c.storage_key, "").label("storage_key"),
]

# Sort keys exposed to the UI, whitelisted so a query-param can never inject
# arbitrary SQL identifiers. Mixed-core/extension keys sort naturally because
# the listing already joins both sides.
_SORTABLE = {
    "number": _CORE.c.number,
    "name": _CORE.c.name,
    "revision": _CORE.c.revision,
    "state": _CORE.c.lifecycle_state,
    "file_name": func.coalesce(_EXT.c.file_name, ""),
    "size": func.coalesce(_EXT.c.file_size_bytes, 0),
    "modified": _CORE.c.modified_on,
}

_MAX_LIMIT = 200


def _as_out(mapping: dict) -> DocumentOut:
    """Validate a joined core+extension row into the flat DocumentOut DTO."""
    return DocumentOut.model_validate(mapping)


def _ext_row_exists(session: Session, vertex_id: UUID) -> bool:
    return session.execute(
        select(func.count()).select_from(_EXT).where(_EXT.c.id == vertex_id)
    ).scalar_one() > 0


def _flat_row(session: Session, tenant_id: UUID, vertex_id: UUID) -> dict | None:
    row = session.execute(
        select(*_CORE_COLS, *_EXT_COLS)
        .join(_EXT, _EXT.c.id == _CORE.c.id, isouter=True)
        .where(
            _CORE.c.id == vertex_id,
            _CORE.c.tenant_id == tenant_id,
        )
    ).one_or_none()
    return dict(row._mapping) if row else None


def find_document(session: Session, tenant_id: UUID, vertex_id: UUID) -> dict | None:
    return _flat_row(session, tenant_id, vertex_id)


def get_document(session: Session, tenant_id: UUID, vertex_id: UUID) -> dict:
    doc = find_document(session, tenant_id, vertex_id)
    if doc is None:
        raise NotFound(f"document {vertex_id} not found in tenant {tenant_id}")
    return doc


def list_documents(
    session: Session,
    tenant_id: UUID,
    *,
    number_like: str | None = None,
    limit: int = 100,
    offset: int = 0,
    sort: str = "number",
    direction: str = "asc",
) -> Page[DocumentOut]:
    """Paged, sorted document listing over the joined core+extension row."""
    limit = min(max(limit, 1), _MAX_LIMIT)
    offset = max(offset, 0)

    conditions = [
        _CORE.c.tenant_id == tenant_id,
        _CORE.c.kind == enums.VertexKind.DOCUMENT,
        _CORE.c.marked_for_deletion.is_(False),
    ]
    if number_like:
        conditions.append(_CORE.c.number.ilike(f"%{number_like}%"))

    order_col = _SORTABLE.get(sort, _CORE.c.number)
    order = order_col.desc() if direction == "desc" else order_col.asc()

    # LEFT JOIN everywhere: metadata-only documents (no extension row yet -
    # seeded ones, imports) must appear with their default attributes.
    total = session.execute(
        select(func.count())
        .select_from(_CORE)
        .join(_EXT, _EXT.c.id == _CORE.c.id, isouter=True)
        .where(*conditions)
    ).scalar_one()
    rows = session.execute(
        select(*_CORE_COLS, *_EXT_COLS)
        .join(_EXT, _EXT.c.id == _CORE.c.id, isouter=True)
        .where(*conditions)
        .order_by(order, _CORE.c.number.asc(), _CORE.c.revision.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Page[DocumentOut](
        items=[from_row(DocumentOut, r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def create_document(
    session: Session,
    tenant_id: UUID,
    data: DocumentCreate,
    actor: str,
    *,
    upload: tuple[str, str | None, BinaryIO] | None = None,
) -> DocumentOut:
    """Create a document vertex plus its extension row (and optional file).

    ``upload`` is ``(filename, content_type, stream)``. Storage runs BEFORE
    the inserts: if the upload itself is invalid (too large, unreadable) we
    fail before touching the database at all. If the database rejects the
    rows afterwards (duplicate number, RLS, ...), the just-stored object is
    deleted again - the transaction rolls the DB side back by itself.
    """
    stored = None
    try:
        if upload is not None:
            filename, content_type, stream = upload
            stored = file_store.save(tenant_id, filename, content_type, stream)

        vertex = vertex_service.create_vertex(session, tenant_id, data, actor=actor)

        ext_values = {
            "id": vertex.id,
            "tenant_id": tenant_id,
            # Defaults keep metadata-only documents valid until a file lands;
            # every column having a DEFAULT is what makes "extension row
            # present, content absent" a legal TSE state.
            "file_is_directory": False,
            "file_name": stored.name if stored else "",
            "file_full_path": stored.name if stored else "",
            "file_size_bytes": stored.size_bytes if stored else 0,
            "file_mime_type": stored.mime_type if stored else "",
            "file_checksum_sha256": stored.checksum_sha256 if stored else "",
            "storage_key": stored.key if stored else "",
        }
        session.execute(insert(_EXT).values(**ext_values))

        logger.info(
            "document.created",
            extra={
                "tenant": str(tenant_id),
                "vertex": str(vertex.id),
                "number": f"{data.prefix}-{data.number}",
                "actor": actor,
                "with_file": bool(stored),
            },
        )
        out = get_document(session, tenant_id, vertex.id)
        return _as_out(get_document(session, tenant_id, vertex.id))
    except Exception:
        if stored is not None:
            file_store.delete(tenant_id, stored.key)
        raise


def update_document(
    session: Session,
    tenant_id: UUID,
    vertex_id: UUID,
    data: VertexUpdate,
    actor: str,
) -> DocumentOut:
    """Core-field updates delegate entirely to the shared vertex service."""
    vertex_service.update_vertex(session, tenant_id, vertex_id, data, actor=actor)
    logger.info("document.updated", extra={"tenant": str(tenant_id), "vertex": str(vertex_id), "actor": actor})
    return _as_out(get_document(session, tenant_id, vertex_id))


def attach_file(
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
    """Upload-or-replace the file content of a document.

    Returns the updated document plus the PREVIOUS storage key; callers must
    delete that key only AFTER the surrounding transaction commits (see the
    route handlers) so a failed commit can never dangle the old pointer.

    The version bump goes through the shared core's optimistic-locking path:
    two users replacing the same file race on the vertex version, and one of
    them loses deterministically instead of last-write-wins.
    """
    current = get_document(session, tenant_id, vertex_id)
    if current["lifecycle_state"] == enums.LifecycleState.RELEASED:
        raise Conflict(
            f"document {current['prefix']}-{current['number']} is Released; "
            "its file can only change via a new revision or the change process"
        )

    stored = file_store.save(tenant_id, filename, content_type, stream)
    old_key = current["storage_key"]

    # Upsert, not update: documents created before the extension row existed
    # (seeded/imported) must gain one on first upload.
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
    # Empty change-set on purpose: the UPDATE statement itself (modified_by/on)
    # plus the core bump_version trigger advance the lock token.
    vertex_service._execute_versioned_update(
        session,
        _CORE,
        {},
        vertex_id=vertex_id,
        tenant_id=tenant_id,
        expected_version=expected_version,
        actor=actor,
    )

    logger.info(
        "document.file.attached",
        extra={"tenant": str(tenant_id), "vertex": str(vertex_id), "key": stored.key, "actor": actor},
    )
    doc = _as_out(get_document(session, tenant_id, vertex_id))
    return doc, old_key


def detach_file(
    session: Session,
    tenant_id: UUID,
    vertex_id: UUID,
    actor: str,
    *,
    expected_version: int,
) -> tuple[DocumentOut, str]:
    """Remove file content but keep the document (metadata-only state)."""
    current = get_document(session, tenant_id, vertex_id)
    if current["lifecycle_state"] == enums.LifecycleState.RELEASED:
        raise Conflict(
            f"document {current['prefix']}-{current['number']} is Released; "
            "its file can only be removed via the change process"
        )
    if not current["storage_key"]:
        raise NotFound(f"document {current['prefix']}-{current['number']}/{current['revision']} has no attached file")

    old_key = current["storage_key"]
    # Detach on a metadata-only document is a no-op by definition; detach on a
    # seeded document without an extension row clears nothing but still bumps
    # the lock token below. Upsert keeps rows uniform where they exist.
    if _ext_row_exists(session, vertex_id):
        session.execute(
            update(_EXT)
            .where(_EXT.c.id == vertex_id, _EXT.c.tenant_id == tenant_id)
            .values(
                file_name="",
                file_full_path="",
                file_size_bytes=0,
                file_mime_type="",
                file_checksum_sha256="",
                storage_key="",
            )
        )
    vertex_service._execute_versioned_update(
        session,
        _CORE,
        {},
        vertex_id=vertex_id,
        tenant_id=tenant_id,
        expected_version=expected_version,
        actor=actor,
    )

    logger.info("document.file.detached", extra={"tenant": str(tenant_id), "vertex": str(vertex_id), "actor": actor})
    doc = _as_out(get_document(session, tenant_id, vertex_id))
    return doc, old_key


def download_document(
    session: Session,
    tenant_id: UUID,
    vertex_id: UUID,
) -> tuple[BinaryIO, str, str, int]:
    """Resolve a document's stored content for streaming.

    Returns ``(stream, filename, mime_type, size_bytes)``. Missing content is
    a ValidationFailed (the document exists; the *capability* is absent),
    which the UI turns into a flash instead of an error page.
    """
    current = get_document(session, tenant_id, vertex_id)
    if not current["storage_key"]:
        raise NotFound(
            f"document {current['prefix']}-{current['number']}/{current['revision']} has no attached file"
        )
    stream, _ = file_store.open_stream(
        tenant_id, current["storage_key"], expected_size=current["file_size_bytes"]
    )
    logger.info(
        "document.file.downloaded",
        extra={"tenant": str(tenant_id), "vertex": str(vertex_id), "key": current["storage_key"]},
    )
    filename = current["file_name"] or f"{current['prefix']}-{current['number']}"
    return stream, filename, current["file_mime_type"] or "application/octet-stream", current["file_size_bytes"]
