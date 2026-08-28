"""EsDevService - proxy Elasticsearch queries from the Developer Tools page.

Credentials never leave the server; the gateway renders JSON for the frontend.
Endpoints serve indices listing, mapping introspection, document counts, and
sample documents for each tenant's vertex/edge indices.
"""
from __future__ import annotations

import logging
from typing import Any

from .es_client import es
from .index_service import vertex_index_name, edge_index_name

logger = logging.getLogger(__name__)


class EsDevService:
    """Read-only helpers for the Developer Tools UI."""

    def __init__(self, client=es):
        self.es = client

    # -- cluster / indices -----------------------------------------------------

    def list_indices(self, slug: str) -> list[dict]:
        """Return _cat/indices rows for one tenant's vertex+edge indices."""
        pattern = f"{self.es.quote_path(slug)}-vertices,{self.es.quote_path(slug)}-edges"
        status, payload = self.es.request(
            "GET", f"/_cat/indices/{pattern}?format=json&h=index,health,status,docs.count,store.size&bytes=b"
        )
        if status != 200:
            return []
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
        return sorted(rows, key=lambda r: r.get("index") or "")

    # -- mappings ----------------------------------------------------------------

    def get_mapping(self, index_name: str) -> dict[str, Any]:
        """Return the full mapping for an index."""
        status, payload = self.es.request(
            "GET", f"/{self.es.quote_path(index_name)}/_mapping?pretty"
        )
        if status == 200:
            return {"ok": True, "data": payload}
        return {"ok": False, "error": payload.get("error", f"HTTP {status}")}

    # -- counts ------------------------------------------------------------------

    def doc_count(self, index_name: str) -> int:
        """Return total document count for an index."""
        status, payload = self.es.request(
            "GET", f"/{self.es.quote_path(index_name)}/_count?pretty"
        )
        if status == 200:
            return int(payload.get("count", 0))
        return 0

    # -- sample documents --------------------------------------------------------

    def sample_documents(self, index_name: str, size: int = 5) -> list[dict]:
        """Return up to *size* sample documents from an index."""
        body = '{"query":{"match_all":{}}, "_source": true}'
        query = f"?size={size}&pretty"
        status, payload = self.es.request(
            "GET", f"/{self.es.quote_path(index_name)}/_search{query}",
            body=body.encode(),
        )
        if status == 200:
            hits = payload.get("hits", {}).get("hits", [])
            return [h.get("_source", {}) for h in hits]
        return []

    # -- search convenience ------------------------------------------------------

    def search_by_kind(self, index_name: str, kind: str, size: int = 10) -> list[dict]:
        """Search an index by vertex kind (Part, Document, EC)."""
        body = f'{{"query":{{"match":{{"kind":"{kind}"}}}}, "_source": true}}'
        query = f"?size={size}&pretty"
        status, payload = self.es.request(
            "GET", f"/{self.es.quote_path(index_name)}/_search{query}",
            body=body.encode(),
        )
        if status == 200:
            hits = payload.get("hits", {}).get("hits", [])
            return [h.get("_source", {}) for h in hits]
        return []


#: Shared singleton wired to the process-wide EsClient.
es_dev = EsDevService(es)
