"""Graph index export: database -> intermediate Elasticsearch-ready file.

One NDJSON file per run under ``database/index`` holds every exported entity
(vertices and edges) as Elasticsearch ``_bulk`` action/document pairs, so the
file can be posted to Elasticsearch verbatim. Each document carries a
deterministic hashing-trick embedding reserved for future semantic search.

Runs are incremental by default: a watermark state file remembers when the
last successful index ran and only rows created after that moment are
exported. Full rebuilds ignore the watermark (used after nuking a tenant's
Elasticsearch indices).

Long runs execute on background threads via :mod:`services.jobs`; the caller
gets a job id back immediately.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
from datetime import date
from datetime import datetime as dt
from pathlib import Path
from uuid import UUID

from sqlalchemy import alias, select

from . import db, jobs, tables, tenant_service
from .errors import NotFound, ValidationFailed

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_DIR = Path(os.getenv("INDEX_DIR", os.path.join(_REPO_ROOT, "database", "index")))
STATE_FILE_NAME = "index_state.json"

EMBEDDING_DIMS = 1024
_BULK_CHUNK_PAIRS = 500

_STATE_LOCK = threading.Lock()
_FILE_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_SLUG_SAFE = re.compile(r"[^a-z0-9-]+")


def slug_for(subdomain: str) -> str:
    slug = _SLUG_SAFE.sub("-", str(subdomain).strip().lower()).strip("-")
    if not slug:
        raise ValidationFailed(f"tenant subdomain '{subdomain}' cannot be turned into an index name")
    return slug


def vertex_index_name(slug: str) -> str:
    return f"{slug}-vertices"


def edge_index_name(slug: str) -> str:
    return f"{slug}-edges"


# ── Embeddings ──────────────────────────────────────────────────────────────


def embed_text(text: str) -> list[float]:
    """Deterministic feature-hashing embedding of arbitrary entity text.

    Tokens are hashed into EMBEDDING_DIMS buckets with a sign flip so the
    vector keeps direction information; L2-normalized for cosine similarity.
    Fully offline and stable across runs; swap in a trained model later
    without changing the file format.
    """
    vec = [0.0] * EMBEDDING_DIMS
    for token in _tokenize(text):
        digest = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest(), "big")
        bucket = digest % EMBEDDING_DIMS
        vec[bucket] += 1.0 if (digest >> 64) & 1 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [round(v / norm, 6) for v in vec]
    return [round(v, 6) for v in vec]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def vertex_embedding_text(doc: dict) -> str:
    parts = [doc.get("kind") or "", doc.get("display_number") or "", doc.get("name") or "",
             doc.get("description") or "", doc.get("revision") or ""]
    for attributes in (doc.get("solution_attributes"), doc.get("tenant_attributes")):
        if isinstance(attributes, dict):
            parts.extend(f"{k}={v}" for k, v in sorted(attributes.items()))
    return " ".join(str(p) for p in parts if p)


def edge_embedding_text(doc: dict) -> str:
    parts = ["edge", doc.get("kind") or "", doc.get("name") or "",
             doc.get("source_display") or "", doc.get("target_display") or ""]
    if isinstance(doc.get("annotation"), dict):
        parts.extend(f"{k}={v}" for k, v in sorted(doc["annotation"].items()))
    return " ".join(str(p) for p in parts if p)


# ── Watermark state (incremental indexing memory) ───────────────────────────


def _load_state() -> dict:
    path = INDEX_DIR / STATE_FILE_NAME
    if not path.is_file():
        return {"tenants": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("index.state.unreadable", extra={"file": str(path)})
        return {"tenants": {}}
    if not isinstance(state.get("tenants"), dict):
        state["tenants"] = {}
    return state


def _save_state(state: dict) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_DIR / f"{STATE_FILE_NAME}.tmp"
    tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    tmp.replace(INDEX_DIR / STATE_FILE_NAME)


def get_watermark(tenant_id: UUID | str) -> dict | None:
    with _STATE_LOCK:
        entry = _load_state()["tenants"].get(str(tenant_id))
        return dict(entry) if entry else None


def clear_watermark(tenant_id: UUID | str) -> bool:
    with _STATE_LOCK:
        state = _load_state()
        existed = state["tenants"].pop(str(tenant_id), None) is not None
        if existed:
            _save_state(state)
        return existed


def _record_run(tenant_id: UUID, entry: dict) -> None:
    with _STATE_LOCK:
        state = _load_state()
        state["tenants"][str(tenant_id)] = entry
        _save_state(state)


def last_indexed_on(tenant_id: UUID | str) -> dt | None:
    entry = get_watermark(tenant_id)
    if not entry or not entry.get("last_indexed_on"):
        return None
    try:
        parsed = dt.fromisoformat(entry["last_indexed_on"])
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


# ── Export ──────────────────────────────────────────────────────────────────


def build_index_file(tenant_id: UUID, *, full: bool = False) -> dict:
    """Export the tenant's graph into one Elasticsearch-bulk NDJSON file.

    Incremental unless ``full``: only rows with created_on strictly after the
    previous run's watermark are included. Returns a run summary and records
    the new watermark only after the file is safely written.
    """
    started_at = dt.now().astimezone()
    with db.admin_session() as session:
        tenant = tenant_service.get_tenant(session, tenant_id)
    slug = slug_for(_edition_safe_subdomain(tenant))
    watermark = None if full else last_indexed_on(tenant_id)

    vertices = _export_vertices(tenant_id=tenant_id, created_after=watermark)
    edges = _export_edges(tenant_id=tenant_id, created_after=watermark)

    pairs: list[tuple[dict, dict]] = []
    for doc in vertices:
        doc["embedding"] = embed_text(vertex_embedding_text(doc))
        pairs.append((bulk_action(vertex_index_name(slug), doc), doc))
    for doc in edges:
        doc["embedding"] = embed_text(edge_embedding_text(doc))
        pairs.append((bulk_action(edge_index_name(slug), doc), doc))

    stamp = started_at.strftime(_FILE_STAMP_FORMAT)
    file_name = f"{slug}-graph-index-{stamp}.ndjson"
    summary = {
        "tenant_id": str(tenant_id),
        "subdomain": tenant["subdomain"],
        "mode": "full" if full else "incremental",
        "previous_watermark": watermark.isoformat() if watermark else None,
        "vertices": len(vertices),
        "edges": len(edges),
        "documents": len(pairs),
        "file": file_name,
        "started_at": started_at.isoformat(),
    }
    if pairs or full:
        write_bulk_file(file_name, pairs)
    else:
        summary["file"] = None
        summary["note"] = "nothing new to index since the last run"

    # The incremental cursor (last_indexed_on) always advances, but the
    # user-facing "data as of" facts only change when a run actually
    # exported documents - a no-op run must not clobber them.
    previous = get_watermark(tenant_id) or {}
    productive = bool(pairs) or full or not previous.get("data_as_of")
    entry: dict = {"last_indexed_on": started_at.isoformat(), "slug": slug}
    if productive:
        entry.update({
            "data_as_of": started_at.isoformat(),
            "mode": summary["mode"],
            "vertices": summary["vertices"],
            "edges": summary["edges"],
            "file": summary["file"],
            "note": summary.get("note"),
        })
    else:
        for key in ("data_as_of", "mode", "vertices", "edges", "file", "note"):
            if key in previous:
                entry[key] = previous[key]
        entry.setdefault("data_as_of", previous.get("last_indexed_on"))
        entry["note"] = previous.get("note") or summary.get("note")

    _record_run(tenant_id, entry)
    logger.info(
        "index.export.done",
        extra={"tenant": str(tenant_id), "mode": summary["mode"], "docs": len(pairs)},
    )
    return summary


def _edition_safe_subdomain(tenant: dict) -> str:
    subdomain = tenant.get("subdomain")
    if not subdomain:
        raise ValidationFailed(f"tenant {tenant.get('id')} has no subdomain; cannot derive index partition")
    return subdomain


def bulk_action(index_name: str, doc: dict) -> dict:
    return {"index": {"_index": index_name, "_id": str(doc.get("id"))}}


def write_bulk_file(file_name: str, pairs: list[tuple[dict, dict]]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    target = INDEX_DIR / file_name
    tmp = INDEX_DIR / f"{file_name}.tmp"
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for action, doc in pairs:
            handle.write(json.dumps(action, separators=(",", ":")))
            handle.write("\n")
            handle.write(json.dumps(doc, separators=(",", ":"), default=_json_default))
            handle.write("\n")
    tmp.replace(target)


def _json_default(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (dt, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _export_vertices(*, tenant_id: UUID, created_after: dt | None) -> list[dict]:
    stmt = select(tables.foundation_vertex).where(tables.foundation_vertex.c.tenant_id == tenant_id)
    if created_after is not None:
        stmt = stmt.where(tables.foundation_vertex.c.created_on > created_after)
    stmt = stmt.order_by(tables.foundation_vertex.c.created_on)
    with db.tenant_session(tenant_id) as session:
        rows = session.execute(stmt).all()
    return [_vertex_doc(row._mapping) for row in rows]


def _export_edges(*, tenant_id: UUID, created_after: dt | None) -> list[dict]:
    source_vertex = alias(tables.foundation_vertex).alias("src_v")
    target_vertex = alias(tables.foundation_vertex).alias("tgt_v")
    edge = tables.foundation_edge
    stmt = (
        select(
            edge,
            source_vertex.c.prefix.label("source_prefix"),
            source_vertex.c.number.label("source_number"),
            source_vertex.c.revision.label("source_revision"),
            source_vertex.c.name.label("source_name"),
            target_vertex.c.prefix.label("target_prefix"),
            target_vertex.c.number.label("target_number"),
            target_vertex.c.revision.label("target_revision"),
            target_vertex.c.name.label("target_name"),
        )
        .join(source_vertex, edge.c.source_vertex_id == source_vertex.c.id)
        .join(target_vertex, edge.c.target_vertex_id == target_vertex.c.id)
        .where(edge.c.tenant_id == tenant_id)
    )
    if created_after is not None:
        stmt = stmt.where(edge.c.created_on > created_after)
    stmt = stmt.order_by(edge.c.created_on)
    with db.tenant_session(tenant_id) as session:
        rows = session.execute(stmt).all()
    return [_edge_doc(row._mapping) for row in rows]

def _vertex_doc(row) -> dict:
    row = dict(row)
    prefix, number = row.get("prefix") or "", row.get("number") or ""
    revision = row.get("revision") or ""
    display = f"{prefix}-{number}" if prefix else number
    return {
        "id": row.get("id"),
        "entity_type": "vertex",
        "tenant_id": row.get("tenant_id"),
        "edition_id": row.get("edition_id"),
        "kind": row.get("kind"),
        "classification_id": row.get("classification_id"),
        "prefix": prefix,
        "number": number,
        "display_number": display,
        "name": row.get("name"),
        "description": row.get("description"),
        "revision": revision,
        "lifecycle_state": row.get("lifecycle_state"),
        "release_on": row.get("release_on"),
        "marked_for_deletion": bool(row.get("marked_for_deletion")),
        "version": row.get("version"),
        "created_by": row.get("created_by"),
        "created_on": row.get("created_on"),
        "modified_by": row.get("modified_by"),
        "modified_on": row.get("modified_on"),
        "solution_attributes": row.get("solution_attributes") or {},
        "tenant_attributes": row.get("tenant_attributes") or {},
    }


def _edge_doc(row) -> dict:
    row = dict(row)

    def display(prefix_key: str, number_key: str, revision_key: str) -> str:
        prefix, number = row.get(prefix_key) or "", row.get(number_key) or ""
        base = f"{prefix}-{number}" if prefix else number
        revision = row.get(revision_key) or ""
        return f"{base}/{revision}" if revision else base

    return {
        "id": row.get("id"),
        "entity_type": "edge",
        "tenant_id": row.get("tenant_id"),
        "edition_id": row.get("edition_id"),
        "kind": row.get("kind"),
        "name": row.get("name"),
        "lifecycle_state": row.get("lifecycle_state"),
        "effective_from": row.get("effective_from"),
        "effective_to": row.get("effective_to"),
        "graph_rule_id": row.get("graph_rule_id"),
        "prefix": row.get("prefix"),
        "source_vertex_id": row.get("source_vertex_id"),
        "source_vertex_kind": row.get("source_vertex_kind"),
        "source_display": display("source_prefix", "source_number", "source_revision"),
        "source_name": row.get("source_name"),
        "target_vertex_id": row.get("target_vertex_id"),
        "target_vertex_kind": row.get("target_vertex_kind"),
        "target_display": display("target_prefix", "target_number", "target_revision"),
        "target_name": row.get("target_name"),
        "version": row.get("version"),
        "created_by": row.get("created_by"),
        "created_on": row.get("created_on"),
        "modified_by": row.get("modified_by"),
        "modified_on": row.get("modified_on"),
        "annotation": row.get("annotation") or {},
        "tenant_attributes": row.get("tenant_attributes") or {},
    }


# ── Background job entry points ─────────────────────────────────────────────


def start_index_job(tenant_id: UUID, *, full: bool = False) -> str:
    with db.admin_session() as session:
        tenant = tenant_service.get_tenant(session, tenant_id)
    name = f"index:{slug_for(tenant['subdomain'])}"
    active = jobs.find_active(name)
    if active is not None:
        raise ValidationFailed(f"an indexing job for this tenant is already {active['status']} (job {active['id']})")

    def target() -> dict:
        return build_index_file(tenant_id, full=full)

    return jobs.start_job(name, target)


# ── File helpers for the admin UI ───────────────────────────────────────────


def list_index_files() -> list[dict]:
    if not INDEX_DIR.is_dir():
        return []
    files = []
    for path in INDEX_DIR.glob("*.ndjson"):
        stat = path.stat()
        match = re.match(r"(?P<slug>.+)-graph-index-\d{8}T\d{6}Z$", path.stem)
        files.append({
            "name": path.name,
            "slug": match.group("slug") if match else None,
            "size_bytes": stat.st_size,
            "modified_on": dt.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        })
    files.sort(key=lambda f: f["modified_on"], reverse=True)
    return files


def resolve_index_file(name: str):
    """Map a submitted file name onto a path inside INDEX_DIR (no escapes)."""
    safe = os.path.basename((name or "").strip())
    if not safe.endswith(".ndjson"):
        raise ValidationFailed(f"'{safe}' is not an index file")
    path = (INDEX_DIR / safe).resolve()
    index_root = INDEX_DIR.resolve()
    if path.parent != index_root:
        raise ValidationFailed(f"'{safe}' is not an index file")
    if not path.is_file():
        raise NotFound(f"index file '{safe}' does not exist")
    return path


def latest_file_for_slug(slug: str) -> dict | None:
    for candidate in list_index_files():
        if candidate["slug"] == slug:
            return candidate
    return None
