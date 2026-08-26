"""SearchService - BM25 keyword search over per-tenant ES indices.

Runs one ``multi_match`` query per tenant index pair (vertices and edges);
Elasticsearch scores both with its default BM25 ranking, so relevance needs
no paid features. Every query is rooted at the signed-in tenant's own
``<slug>-vertices`` / ``<slug>-edges`` indices, so cross-tenant leakage is
impossible by construction.

Why a class
-----------
Search composes two collaborators (EsClient transport, tenant/index naming)
injected at construction; results are normalized into view-ready rows with
deep links back into the graph workspace. Stub the client in tests, or add
semantic/vector search later as additional methods on this one service.

How to extend (future scenarios)
--------------------------------
* Vector/semantic search (Phase 3 roadmap) -> add ``semantic()`` here using
  the embedding field already mapped on every document.
* Saved searches -> persistence lives in a new service; ranking stays here.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from uuid import UUID

from markupsafe import escape

from . import db, index_service
from .tenant_service import tenants
from .errors import ServiceError, ValidationFailed
from .es_client import es

logger = logging.getLogger(__name__)

_MIN_QUERY_LENGTH = 2
_DEFAULT_LIMIT = 20
_HIGHLIGHT_FRAGMENT_SIZE = 120

_VERTEX_FIELDS = ["name^4", "display_number.text^3", "number^2", "kind^2", "description"]
_EDGE_FIELDS = ["name^4", "kind^2", "source_display.text^2", "target_display.text^2"]


class SearchService:
    def __init__(self, client):
        self.es = client

    def search(self, tenant_id: UUID, query: str, *, limit: int = _DEFAULT_LIMIT) -> dict:
        """BM25-search vertices and edges of one tenant; returns ranked rows."""
        text = (query or "").strip()
        if len(text) < _MIN_QUERY_LENGTH:
            raise ValidationFailed(f"search needs at least {_MIN_QUERY_LENGTH} characters")
        limit = max(1, min(limit, 50))

        with db.admin_session() as session:
            tenant = tenants.get(session, tenant_id)
        slug = index_service.slug_for(tenant["subdomain"])

        vertex_hits = self._search_index(
            index_service.vertex_index_name(slug), text, fields=_VERTEX_FIELDS, size=limit,
        )
        edge_hits = self._search_index(
            index_service.edge_index_name(slug), text, fields=_EDGE_FIELDS, size=limit,
        )

        rows = [self._vertex_row(hit) for hit in vertex_hits] + \
               [self._edge_row(hit) for hit in edge_hits]
        rows.sort(key=lambda r: r["score"], reverse=True)
        return {
            "query": text,
            "total": len(rows),
            "vertices": len(vertex_hits),
            "edges": len(edge_hits),
            "rows": rows[:limit],
        }

    # ── helpers ──────────────────────────────────────────────────────────────

    def _search_index(self, index: str, text: str, *, fields: list[str], size: int) -> list[dict]:
        body = {
            "size": size,
            "query": {
                "multi_match": {
                    "query": text,
                    "fields": fields,
                    "type": "best_fields",
                    "operator": "or",
                    # AUTO fuzziness (2 edits for long terms) so spelling variants
                    # like aluminium/aluminum or small typos still match; exact
                    # matches keep their scoring edge over fuzzy ones.
                    "fuzziness": "AUTO",
                }
            },
            "highlight": {
                "pre_tags": ["<mark>"],
                "post_tags": ["</mark>"],
                "fragment_size": _HIGHLIGHT_FRAGMENT_SIZE,
                "number_of_fragments": 1,
                "fields": {"name": {}, "description": {},
                           "source_display.text": {}, "target_display.text": {}},
            },
        }
        path = f"/{urllib.parse.quote(index)}/_search"
        status, payload = self.es.request("GET", path, body=json.dumps(body).encode())
        if status != 200:
            raise ServiceError(
                f"elasticsearch search on '{index}' failed: HTTP {status} {payload.get('error', '')}"
            )
        return [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                "source": hit.get("_source", {}),
                "highlights": [
                    fragment
                    for fragments in (hit.get("highlight") or {}).values()
                    for fragment in fragments
                ],
            }
            for hit in payload.get("hits", {}).get("hits", [])
        ]

    @staticmethod
    def _safe_highlight(fragment: str) -> str:
        """Escape stored text but re-enable only Elasticsearch's <mark> tags."""
        escaped = str(escape(fragment or ""))
        return escaped.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")

    def _vertex_row(self, hit: dict) -> dict:
        doc = hit["source"]
        display = doc.get("display_number") or str(doc.get("number") or hit["id"])
        title = f"{display} {doc.get('name') or ''}".strip()
        attributes = doc.get("solution_attributes") or {}
        subtitle_bits = [f"{k}: {v}" for k, v in sorted(attributes.items())][:2]
        if doc.get("description"):
            subtitle_bits.append(doc["description"])
        return {
            "entity_type": "vertex",
            "id": str(doc.get("id") or hit["id"]),
            "display": display,
            "name": doc.get("name") or "",
            "kind": doc.get("kind"),
            "title": title,
            "subtitle": " · ".join(subtitle_bits),
            "lifecycle_state": doc.get("lifecycle_state"),
            "url": f"/graph?tab=view&vertex={urllib.parse.quote(display)}",
            "score": round(hit["score"], 4),
            "highlights": hit["highlights"],
            "highlight_html": self._safe_highlight(hit["highlights"][0]) if hit["highlights"] else "",
        }

    def _edge_row(self, hit: dict) -> dict:
        doc = hit["source"]
        source = doc.get("source_display") or doc.get("source_vertex_id")
        target = doc.get("target_display") or doc.get("target_vertex_id")
        name = doc.get("name") or ""
        return {
            "entity_type": "edge",
            "id": str(doc.get("id") or hit["id"]),
            "kind": doc.get("kind"),
            "title": f"{doc.get('kind')}: {source} -> {target}" + (f" - {name}" if name else ""),
            "subtitle": name or None,
            "lifecycle_state": doc.get("lifecycle_state"),
            "url": f"/graph?tab=edge&edit={doc.get('id') or hit['id']}",
            "score": round(hit["score"], 4),
            "highlights": hit["highlights"],
            "highlight_html": self._safe_highlight(hit["highlights"][0]) if hit["highlights"] else "",
        }


#: Shared singleton wired to the process-wide EsClient.
searcher = SearchService(es)
