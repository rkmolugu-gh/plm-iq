"""Ingest intermediate index files into Elasticsearch.

Talks to a community-edition (basic license) Elasticsearch over its plain
REST API using only the standard library, so no client/server version
coupling and no paid features: index CRUD, ``_bulk``, ``_cat`` and cluster
health only. No security/ML/watcher/snapshot-to-S3 APIs are touched; API-key
or basic auth headers are sent when configured.

Tenancy model: everything is rooted at the tenant slug - intermediate files
are named ``<slug>-graph-index-<stamp>.ndjson`` and each tenant owns one
index pair (``<slug>-vertices`` / ``<slug>-edges``). BEFORE any ingest every
action line is validated against that partitioning - the target index must
be the tenant's own index and the document's ``tenant_id`` must match it -
and ingestion is aborted on the first violation.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from . import db, index_service, jobs, tenant_service
from .errors import ServiceError, ValidationFailed

logger = logging.getLogger(__name__)

_BULK_CHUNK_PAIRS = 500


def _es_url() -> str:
    return os.getenv("ELASTICSEARCH_URL", "http://localhost:9200").rstrip("/")


def _timeout() -> float:
    return float(os.getenv("ELASTICSEARCH_TIMEOUT", "30"))


# ── Minimal REST client (basic-license endpoints only) ──────────────────────


def _request(method: str, path: str, *, body: bytes | None = None, content_type: str = "application/json") -> tuple[int, dict | list]:
    request = urllib.request.Request(f"{_es_url()}{path}", data=body, method=method)
    request.add_header("Accept", "application/json")
    api_key = os.getenv("ELASTICSEARCH_API_KEY")
    username = os.getenv("ELASTICSEARCH_USERNAME") or os.getenv("ES_USER") or "elastic"
    password = os.getenv("ELASTICSEARCH_PASSWORD", "") or os.getenv("ES_PASSWORD", "")
    if api_key:
        request.add_header("Authorization", f"ApiKey {api_key}")
    elif username:
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    if body is not None:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=_timeout()) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        return exc.code, {"error": detail}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ServiceError(f"elasticsearch unreachable at {_es_url()}: {exc}") from exc


def _root_info() -> dict:
    status, payload = _request("GET", "/")
    if status != 200:
        raise ServiceError(f"elasticsearch responded with HTTP {status}: {payload.get('error', '')}")
    return payload  # type: ignore[return-value]


def cluster_status() -> dict:
    """Connection summary for the admin page; never raises when offline."""
    try:
        info = _root_info()
    except ServiceError as exc:
        return {"online": False, "url": _es_url(), "version": None, "error": str(exc)}
    return {"online": True, "url": _es_url(), "version": info.get("version", {}).get("number"), "error": None}


def ping() -> bool:
    try:
        _root_info()
    except ServiceError:
        return False
    return True


def _known_slugs() -> list[str]:
    with db.admin_session() as session:
        tenants = tenant_service.list_tenants(session, limit=1000).items
    return sorted({index_service.slug_for(t.subdomain) for t in tenants})


def indices_status(*slugs: str) -> list[dict]:
    """_cat rows for tenant-rooted search indices; all known tenants by default."""
    patterns = ",".join(f"{urllib.parse.quote(slug)}-*" for slug in (slugs or _known_slugs()))
    if not patterns:
        return []
    query = urllib.parse.urlencode({
        "format": "json",
        "h": "index,health,status,docs.count,store.size",
        "bytes": "b",
    })
    _, payload = _request("GET", f"/_cat/indices/{patterns}?{query}")
    rows = []
    for raw in payload if isinstance(payload, list) else []:
        docs = raw.get("docs.count")
        store = raw.get("store.size")
        rows.append({
            "index": raw.get("index"),
            "health": raw.get("health"),
            "state": raw.get("status"),
            "docs_count": int(docs) if docs not in (None, "") else 0,
            "store_bytes": int(store) if store not in (None, "") else 0,
        })
    rows.sort(key=lambda r: r["index"] or "")
    return rows


# ── Mappings ────────────────────────────────────────────────────────────────


def _embedding_field() -> dict:
    return {"type": "dense_vector", "dims": index_service.EMBEDDING_DIMS, "index": True, "similarity": "cosine"}


def _keyword(text_subfield: bool = False) -> dict:
    field: dict = {"type": "keyword"}
    if text_subfield:
        field["fields"] = {"text": {"type": "text"}}
    return field


_VERTEX_MAPPING: dict = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "id": _keyword(),
            "entity_type": _keyword(),
            "tenant_id": _keyword(),
            "edition_id": _keyword(),
            "kind": _keyword(),
            "classification_id": _keyword(),
            "prefix": _keyword(),
            "number": _keyword(),
            "display_number": _keyword(text_subfield=True),
            "name": {"type": "text", "fields": {"keyword": _keyword()}},
            "description": {"type": "text"},
            "revision": _keyword(),
            "lifecycle_state": _keyword(),
            "release_on": {"type": "date"},
            "marked_for_deletion": {"type": "boolean"},
            "version": {"type": "long"},
            "created_by": _keyword(),
            "created_on": {"type": "date"},
            "modified_by": _keyword(),
            "modified_on": {"type": "date"},
            "solution_attributes": {"type": "flattened"},
            "tenant_attributes": {"type": "flattened"},
            "embedding": _embedding_field(),
        }
    },
}

_EDGE_MAPPING: dict = {
    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
    "mappings": {
        "properties": {
            "id": _keyword(),
            "entity_type": _keyword(),
            "tenant_id": _keyword(),
            "edition_id": _keyword(),
            "kind": _keyword(),
            "name": {"type": "text", "fields": {"keyword": _keyword()}},
            "lifecycle_state": _keyword(),
            "effective_from": {"type": "date"},
            "effective_to": {"type": "date"},
            "graph_rule_id": _keyword(),
            "prefix": _keyword(),
            "source_vertex_id": _keyword(),
            "source_vertex_kind": _keyword(),
            "source_display": _keyword(text_subfield=True),
            "source_name": {"type": "text"},
            "target_vertex_id": _keyword(),
            "target_vertex_kind": _keyword(),
            "target_display": _keyword(text_subfield=True),
            "target_name": {"type": "text"},
            "version": {"type": "long"},
            "created_by": _keyword(),
            "created_on": {"type": "date"},
            "modified_by": _keyword(),
            "modified_on": {"type": "date"},
            "annotation": {"type": "flattened"},
            "tenant_attributes": {"type": "flattened"},
            "embedding": _embedding_field(),
        }
    },
}


def ensure_indices(slug: str) -> list[str]:
    """Create the tenant's vertex/edge indices when missing; returns names."""
    created = []
    for name, mapping in (
        (index_service.vertex_index_name(slug), _VERTEX_MAPPING),
        (index_service.edge_index_name(slug), _EDGE_MAPPING),
    ):
        status, _ = _request("HEAD", f"/{urllib.parse.quote(name)}")
        if status == 200:
            continue
        status, payload = _request("PUT", f"/{urllib.parse.quote(name)}", body=json.dumps(mapping).encode())
        if status not in (200, 201):
            raise ServiceError(f"could not create index '{name}': HTTP {status} {payload.get('error', '')}")
        created.append(name)
    return created


# ── Partition validation (runs before any write) ────────────────────────────


def read_bulk_pairs(path) -> list[tuple[dict, dict]]:
    pairs: list[tuple[dict, dict]] = []
    with open(path, encoding="utf-8") as handle:
        pending_action: dict | None = None
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except ValueError as exc:
                raise ValidationFailed(f"{path.name} line {line_no} is not valid JSON") from exc
            if pending_action is None:
                if not isinstance(parsed, dict) or "index" not in parsed:
                    raise ValidationFailed(f"{path.name} line {line_no} is not an index action")
                pending_action = parsed
            else:
                pairs.append((pending_action, parsed))
                pending_action = None
    if pending_action is not None:
        raise ValidationFailed(f"{path.name} ends with a dangling action line")
    return pairs


def validate_partition(pairs: list[tuple[dict, dict]], slug_by_tenant: dict[str, str]) -> dict[str, int]:
    """Abort unless every document targets its own tenant's index partition."""
    counts: dict[str, int] = {}
    for action, doc in pairs:
        meta = action.get("index") or {}
        target_index = meta.get("_index")
        tenant_id = doc.get("tenant_id")
        entity_type = doc.get("entity_type")
        if not tenant_id or not entity_type:
            raise ValidationFailed(f"document {meta.get('_id')} lacks tenant_id/entity_type")
        slug = slug_by_tenant.get(str(tenant_id))
        if slug is None:
            raise ValidationFailed(f"document {meta.get('_id')} belongs to unknown tenant {tenant_id}")
        expected = (
            index_service.vertex_index_name(slug)
            if entity_type == "vertex"
            else index_service.edge_index_name(slug)
        )
        if target_index != expected:
            raise ValidationFailed(
                f"partition violation: tenant {slug} document {meta.get('_id')} targets "
                f"'{target_index}' instead of its own '{expected}'"
            )
        if meta.get("_id") and doc.get("id") and str(meta["_id"]) != str(doc["id"]):
            raise ValidationFailed(f"action id {meta['_id']} does not match document id {doc['id']}")
        counts[target_index] = counts.get(target_index, 0) + 1
    return counts


# ── Ingest / nuke ───────────────────────────────────────────────────────────


def ingest_file(path) -> dict:
    """Validate then bulk-index one intermediate file. Returns a summary."""
    pairs = read_bulk_pairs(path)
    if not pairs:
        return {"file": path.name, "documents": 0, "indices": [], "tenants": []}

    tenant_ids = sorted({str(doc.get("tenant_id")) for _, doc in pairs})
    slug_by_tenant: dict[str, str] = {}
    subdomains: dict[str, str] = {}
    with db.admin_session() as session:
        for tenant_id in tenant_ids:
            tenant = tenant_service.find_tenant(session, tenant_id)
            if tenant is None:
                raise ValidationFailed(f"file references unknown tenant {tenant_id}")
            slug_by_tenant[tenant_id] = index_service.slug_for(tenant["subdomain"])
            subdomains[tenant_id] = tenant["subdomain"]

    counts = validate_partition(pairs, slug_by_tenant)

    touched_indices = []
    for slug in sorted(set(slug_by_tenant.values())):
        touched_indices.extend(ensure_indices(slug))

    indexed = 0
    for chunk_start in range(0, len(pairs), _BULK_CHUNK_PAIRS):
        indexed += _bulk_chunk(pairs[chunk_start:chunk_start + _BULK_CHUNK_PAIRS])

    logger.info("es.ingest.done", extra={"file": path.name, "docs": indexed})
    return {
        "file": path.name,
        "documents": indexed,
        "per_index": counts,
        "indices": touched_indices,
        "tenants": [subdomains[tid] for tid in tenant_ids],
    }


def _bulk_chunk(pairs: list[tuple[dict, dict]]) -> int:
    body = "".join(
        json.dumps(action, separators=(",", ":")) + "\n" + json.dumps(doc, separators=(",", ":")) + "\n"
        for action, doc in pairs
    ).encode("utf-8")
    status, payload = _request("POST", "/_bulk?refresh=true", body=body, content_type="application/x-ndjson")
    if status != 200:
        raise ServiceError(f"elasticsearch _bulk failed with HTTP {status}: {payload.get('error', '')}")
    if payload.get("errors"):
        first = next(item for item in payload["items"] if item.get("index", {}).get("error"))
        error = first["index"]["error"]
        raise ServiceError(f"elasticsearch rejected documents: {error.get('type')}: {error.get('reason')}")
    return len(pairs)


def nuke_tenant(tenant_id) -> dict:
    """Delete every Elasticsearch index of one tenant and reset the watermark."""
    with db.admin_session() as session:
        tenant = tenant_service.get_tenant(session, tenant_id)
    slug = index_service.slug_for(tenant["subdomain"])

    own = {
        index_service.vertex_index_name(slug),
        index_service.edge_index_name(slug),
    }
    existing = [row for row in indices_status(slug) if row["index"] in own]
    deleted = []
    if existing:
        names = ",".join(urllib.parse.quote(row["index"]) for row in existing)
        status, payload = _request("DELETE", f"/{names}")
        if status not in (200, 404):
            raise ServiceError(f"could not delete indices for '{slug}': HTTP {status} {payload.get('error', '')}")
        deleted = [row["index"] for row in existing]

    watermark_cleared = index_service.clear_watermark(tenant_id)
    logger.info(
        "es.nuke.done",
        extra={"tenant": str(tenant_id), "indices": len(deleted), "watermark_cleared": watermark_cleared},
    )
    return {
        "tenant": tenant["subdomain"],
        "deleted_indices": deleted,
        "documents_removed": sum(row["docs_count"] for row in existing),
        "watermark_cleared": watermark_cleared,
    }


def start_ingest_job(path) -> str:
    name = f"ingest:{path.name}"
    active = jobs.find_active("ingest:")
    if active is not None:
        raise ValidationFailed(f"an ingest job is already {active['status']} (job {active['id']})")

    def target() -> dict:
        return ingest_file(path)

    return jobs.start_job(name, target)
