"""PostgreSQL FTS dev / admin tools — mirrors es_dev_service.py.

Provides stats, health checks, and index introspection for the PG full-text
search platform. Used by the Developer Tools page when SEARCH_PLATFORM=POSTGRES.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select, text

from . import db, tables
from .errors import ValidationFailed

logger = logging.getLogger(__name__)


class PostgresDevService:
    """Dev/admin service for PostgreSQL full-text search (GIN tsvector indices)."""

    def __init__(self):
        self.name = "postgres_dev"

    def stats(self, tenant_id: UUID) -> dict:
        """Return vertex/edge counts from the search tables."""
        sv = tables.search_vertex
        se = tables.search_edge
        try:
            with db.admin_session() as session:
                vertex_count = session.execute(
                    select(func.count()).select_from(sv).where(sv.c.tenant_id == tenant_id)
                ).scalar() or 0
                edge_count = session.execute(
                    select(func.count()).select_from(se).where(se.c.tenant_id == tenant_id)
                ).scalar() or 0
            return {
                "platform": "POSTGRES",
                "vertex_count": vertex_count,
                "edge_count": edge_count,
            }
        except Exception as exc:
            logger.error("pg_dev.stats.failed", extra={"error": str(exc)})
            return {"platform": "POSTGRES", "error": str(exc)}

    def health(self) -> dict:
        """Return overall health of the PG search platform."""
        try:
            with db.admin_session() as session:
                session.execute(text("SELECT 1"))
                # Verify search tables exist and are readable
                session.execute(text("SELECT COUNT(*) FROM plmiqdb.search_vertex LIMIT 1"))
                session.execute(text("SELECT COUNT(*) FROM plmiqdb.search_edge LIMIT 1"))
            return {"platform": "POSTGRES", "status": "ok"}
        except Exception as exc:
            logger.error("pg_dev.health.failed", extra={"error": str(exc)})
            return {"platform": "POSTGRES", "status": "error", "detail": str(exc)}

    def index_size(self, tenant_id: UUID) -> dict:
        """Return approximate size of the search index tables in bytes."""
        try:
            with db.admin_session() as session:
                sv_size = session.execute(
                    text(
                        "SELECT pg_total_relation_size('plmiqdb.search_vertex') "
                        "- pg_indexes_size('plmiqdb.search_vertex')"
                    )
                ).scalar() or 0
                se_size = session.execute(
                    text(
                        "SELECT pg_total_relation_size('plmiqdb.search_edge') "
                        "- pg_indexes_size('plmiqdb.search_edge')"
                    )
                ).scalar() or 0
                total_size = session.execute(
                    text(
                        "SELECT pg_total_relation_size('plmiqdb.search_vertex') + "
                        "pg_total_relation_size('plmiqdb.search_edge')"
                    )
                ).scalar() or 0
            return {
                "platform": "POSTGRES",
                "search_vertex_bytes": int(sv_size),
                "search_edge_bytes": int(se_size),
                "total_bytes": int(total_size),
            }
        except Exception as exc:
            logger.error("pg_dev.index_size.failed", extra={"error": str(exc)})
            return {"platform": "POSTGRES", "error": str(exc)}

    def last_indexed(self, tenant_id: UUID) -> dict | None:
        """Return the most recently modified search record for a tenant."""
        sv = tables.search_vertex
        se = tables.search_edge
        try:
            with db.admin_session() as session:
                vertex_max = session.execute(
                    select(func.max(sv.c.modified_on)).where(sv.c.tenant_id == tenant_id)
                ).scalar()
                edge_max = session.execute(
                    select(func.max(se.c.modified_on)).where(se.c.tenant_id == tenant_id)
                ).scalar()
            if vertex_max is None and edge_max is None:
                return None
            latest = vertex_max if vertex_max else edge_max
            if vertex_max and edge_max and edge_max > vertex_max:
                latest = edge_max
            return {
                "platform": "POSTGRES",
                "last_vertex_modified": str(vertex_max) if vertex_max else None,
                "last_edge_modified": str(edge_max) if edge_max else None,
                "last_indexed": str(latest),
            }
        except Exception as exc:
            logger.error("pg_dev.last_indexed.failed", extra={"error": str(exc)})
            return None

    def search_index_info(self) -> dict:
        """Return info about the tsvector indexes (GIN index names and columns)."""
        try:
            with db.admin_session() as session:
                rows = session.execute(
                    text("""
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE schemaname = 'plmiqdb'
                          AND tablename IN ('search_vertex', 'search_edge')
                          AND indexdef ILIKE '%tsvector%'
                        ORDER BY tablename, indexname
                    """)
                ).fetchall()
            indices = [
                {"index": r[0], "definition": r[1]}
                for r in rows
            ]
            return {
                "platform": "POSTGRES",
                "fts_indexes": indices,
                "count": len(indices),
            }
        except Exception as exc:
            logger.error("pg_dev.search_index_info.failed", extra={"error": str(exc)})
            return {"platform": "POSTGRES", "error": str(exc)}

    def reset_index(self, tenant_id: UUID) -> dict:
        """Delete all search documents for a tenant (for reindexing)."""
        try:
            with db.tenant_session(tenant_id) as session:
                session.execute(
                    text("DELETE FROM plmiqdb.search_vertex WHERE tenant_id = :tid"),
                    {"tid": tenant_id},
                )
                session.execute(
                    text("DELETE FROM plmiqdb.search_edge WHERE tenant_id = :tid"),
                    {"tid": tenant_id},
                )
                session.commit()
            logger.info("pg_dev.reset_index.done", extra={"tenant": str(tenant_id)})
            return {"platform": "POSTGRES", "status": "reset", "tenant_id": str(tenant_id)}
        except Exception as exc:
            logger.error("pg_dev.reset_index.failed", extra={"error": str(exc)})
            return {"platform": "POSTGRES", "error": str(exc)}

    def sample_search(self, tenant_id: UUID, query: str, limit: int = 5) -> dict:
        """Run a sample FTS query and return results with ts_rank scores."""
        sv = tables.search_vertex
        se = tables.search_edge
        tsquery = func.plainto_tsquery("english", query)
        try:
            with db.tenant_session(tenant_id) as session:
                v_rows = session.execute(
                    select(
                        sv.c.id,
                        sv.c.kind,
                        sv.c.name,
                        sv.c.display_number,
                        func.ts_rank(sv.c.text_vector, tsquery).label("score"),
                    )
                    .where(sv.c.tenant_id == tenant_id)
                    .where(sv.c.text_vector.op("@@")(tsquery))
                    .order_by(func.ts_rank(sv.c.text_vector, tsquery).desc())
                    .limit(limit)
                ).fetchall()

                e_rows = session.execute(
                    select(
                        se.c.id,
                        se.c.kind,
                        se.c.name,
                        se.c.source_display,
                        se.c.target_display,
                        func.ts_rank(se.c.text_vector, tsquery).label("score"),
                    )
                    .where(se.c.tenant_id == tenant_id)
                    .where(se.c.text_vector.op("@@")(tsquery))
                    .order_by(func.ts_rank(se.c.text_vector, tsquery).desc())
                    .limit(limit)
                ).fetchall()

            vertices = [
                {
                    "id": str(r[0]),
                    "kind": r[1],
                    "name": r[2],
                    "display_number": r[3],
                    "score": round(float(r[4]), 4),
                }
                for r in v_rows
            ]
            edges = [
                {
                    "id": str(r[0]),
                    "kind": r[1],
                    "name": r[2],
                    "source_display": r[3],
                    "target_display": r[4],
                    "score": round(float(r[5]), 4),
                }
                for r in e_rows
            ]
            return {
                "platform": "POSTGRES",
                "query": query,
                "vertices": vertices,
                "edges": edges,
            }
        except Exception as exc:
            logger.error("pg_dev.sample_search.failed", extra={"error": str(exc)})
            return {"platform": "POSTGRES", "error": str(exc)}


#: Singleton instance — returned by search_service_factory when SEARCH_PLATFORM=POSTGRES.
pg_dev = PostgresDevService()
