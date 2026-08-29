"""PostgreSQL full-text search service using ts_rank and ts_headline.

Mirrors the Elasticsearch SearchService API. When SEARCH_PLATFORM=POSTGRES,
``search_service_factory`` returns the ``pg_search`` singleton from this module
instead of the ES-backed ``searcher``.

PostgreSQL FTS is configured with:
  - English text search config (to_tsvector/to_tsquery)
  - Weighted fields: name (A), display_number (B), kind (C), description (D)
  - GIN index on text_vector for fast lookups
  - ts_rank for relevance scoring, ts_headline for result highlighting
"""
from __future__ import annotations

import logging
import urllib.parse
from uuid import UUID

from markupsafe import escape
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import TSVector
from sqlalchemy.orm import Session

from . import db, tables
from .errors import ValidationFailed

logger = logging.getLogger(__name__)

_MIN_QUERY_LENGTH = 2
_DEFAULT_LIMIT = 20
_HIGHLIGHT_FRAGMENT_SIZE = 120


def _safe_highlight(fragment: str) -> str:
    """Escape text but re-enable only the <mark> tag inserted by ts_headline."""
    escaped = str(escape(fragment or ""))
    return escaped.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")


class PostgresSearchService:
    """Search service backed by PostgreSQL full-text search (GIN index on text_vector)."""

    def __init__(self):
        self.name = "postgres_fts"

    def search(self, tenant_id: UUID, query: str, *, limit: int = _DEFAULT_LIMIT) -> dict:
        """FTS-search vertices and edges of one tenant; returns ranked rows."""
        text = (query or "").strip()
        if len(text) < _MIN_QUERY_LENGTH:
            raise ValidationFailed(f"search needs at least {_MIN_QUERY_LENGTH} characters")
        limit = max(1, min(limit, 50))

        vertex_rows = self._search_vertices(tenant_id, text, limit)
        edge_rows = self._search_edges(tenant_id, text, limit)

        rows = vertex_rows + edge_rows
        rows.sort(key=lambda r: r["score"], reverse=True)
        return {
            "query": text,
            "total": len(rows),
            "vertices": len(vertex_rows),
            "edges": len(edge_rows),
            "rows": rows[:limit],
        }

    # ── vertex search ─────────────────────────────────────────────────────────

    def _search_vertices(self, tenant_id: UUID, query: str, limit: int) -> list[dict]:
        sv = tables.search_vertex
        tsquery = func.plainto_tsquery("english", query)
        headline_expr = func.ts_headline(
            "english",
            func.coalesce(sv.c.name, text("''")),
            tsquery,
            f"StartSel=<mark>, StopSel=</mark>, MaxWords={_HIGHLIGHT_FRAGMENT_SIZE}, "
            f"MinWords=15, MaxFragments=1",
        )
        stmt = (
            select(
                sv.c.id,
                sv.c.kind,
                sv.c.name,
                sv.c.description,
                sv.c.classification_id,
                sv.c.prefix,
                sv.c.number,
                sv.c.display_number,
                sv.c.revision,
                sv.c.lifecycle_state,
                func.ts_rank(sv.c.text_vector, tsquery).label("score"),
                headline_expr.label("highlight"),
            )
            .where(sv.c.tenant_id == tenant_id)
            .where(sv.c.text_vector.op("@@")(tsquery))
            .order_by(func.ts_rank(sv.c.text_vector, tsquery).desc())
            .limit(limit)
        )
        with db.tenant_session(tenant_id) as session:
            rows = session.execute(stmt).all()
        return [self._vertex_row(r._mapping) for r in rows]

    @staticmethod
    def _vertex_row(row: dict) -> dict:
        display = row.get("display_number") or str(row.get("number") or row.get("id"))
        name = row.get("name") or ""
        title = f"{display} {name}".strip()
        highlight = row.get("highlight") or ""
        return {
            "entity_type": "vertex",
            "id": str(row.get("id")),
            "display": display,
            "name": name,
            "kind": row.get("kind"),
            "title": title,
            "subtitle": row.get("description") or "",
            "lifecycle_state": row.get("lifecycle_state"),
            "url": f"/graph?tab=view&vertex={urllib.parse.quote(display)}",
            "score": round(float(row.get("score") or 0), 4),
            "highlights": [highlight] if highlight else [],
            "highlight_html": _safe_highlight(highlight),
        }

    # ── edge search ───────────────────────────────────────────────────────────

    def _search_edges(self, tenant_id: UUID, query: str, limit: int) -> list[dict]:
        se = tables.search_edge
        tsquery = func.plainto_tsquery("english", query)
        headline_expr = func.ts_headline(
            "english",
            func.coalesce(se.c.name, text("''")),
            tsquery,
            f"StartSel=<mark>, StopSel=</mark>, MaxWords={_HIGHLIGHT_FRAGMENT_SIZE}, "
            f"MinWords=15, MaxFragments=1",
        )
        stmt = (
            select(
                se.c.id,
                se.c.kind,
                se.c.name,
                se.c.lifecycle_state,
                se.c.source_vertex_id,
                se.c.source_vertex_kind,
                se.c.source_display,
                se.c.source_name,
                se.c.target_vertex_id,
                se.c.target_vertex_kind,
                se.c.target_display,
                se.c.target_name,
                func.ts_rank(se.c.text_vector, tsquery).label("score"),
                headline_expr.label("highlight"),
            )
            .where(se.c.tenant_id == tenant_id)
            .where(se.c.text_vector.op("@@")(tsquery))
            .order_by(func.ts_rank(se.c.text_vector, tsquery).desc())
            .limit(limit)
        )
        with db.tenant_session(tenant_id) as session:
            rows = session.execute(stmt).all()
        return [self._edge_row(r._mapping) for r in rows]

    @staticmethod
    def _edge_row(row: dict) -> dict:
        source = row.get("source_display") or str(row.get("source_vertex_id") or "")
        target = row.get("target_display") or str(row.get("target_vertex_id") or "")
        kind = row.get("kind") or "edge"
        name = row.get("name") or ""
        title = f"{kind}: {source} -> {target}" + (f" - {name}" if name else "")
        highlight = row.get("highlight") or ""
        return {
            "entity_type": "edge",
            "id": str(row.get("id")),
            "kind": kind,
            "title": title,
            "subtitle": name or None,
            "lifecycle_state": row.get("lifecycle_state"),
            "url": f"/graph?tab=edge&edit={row.get('id')}",
            "score": round(float(row.get("score") or 0), 4),
            "highlights": [highlight] if highlight else [],
            "highlight_html": _safe_highlight(highlight),
        }

    def health(self) -> dict:
        """Return a health check dict."""
        try:
            with db.admin_session() as session:
                session.execute(text("SELECT 1"))
            return {"platform": "POSTGRES", "search": "ok"}
        except Exception as exc:
            logger.error("postgres_search.health.failed", extra={"error": str(exc)})
            return {"platform": "POSTGRES", "search": "error", "detail": str(exc)}


#: Singleton instance — returned by search_service_factory when SEARCH_PLATFORM=POSTGRES.
pg_search = PostgresSearchService()
