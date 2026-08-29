"""PostgreSQL full-text search index builder — upserts into search_vertex / search_edge.

Mirrors the Elasticsearch IndexBuilder API. When SEARCH_PLATFORM=POSTGRES,
``search_service_factory`` returns the ``pg_indexer`` singleton from this module.

The text_vector column is maintained via weighted to_tsvector:
  - name:          weight A  (highest)
  - display_number: weight B
  - kind:          weight C
  - description:   weight D  (lowest)

Upserts use INSERT ... ON CONFLICT (id) DO UPDATE so re-indexing is safe.
"""
from __future__ import annotations

import logging
from datetime import date, datetime as dt
from uuid import UUID

from sqlalchemy import delete, func, text
from sqlalchemy.dialects.postgresql import JSONB, TSVector

from . import db, tables
from .errors import ValidationFailed

logger = logging.getLogger(__name__)

#: English-language text search config — shared across all tsvector operations.
_TS_LANG = "english"


def _tsvector_expr(
    name: str | None,
    display_number: str | None,
    kind: str | None,
    description: str | None,
) -> str:
    """Return a SQL expression that builds a weighted tsvector.

    Builds:
      setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
      setweight(to_tsvector('english', coalesce(display_number, '')), 'B') ||
      setweight(to_tsvector('english', coalesce(kind, '')), 'C') ||
      setweight(to_tsvector('english', coalesce(description, '')), 'D')
    """
    def _w(col: str | None) -> str:
        return f"setweight(to_tsvector('{_TS_LANG}', coalesce({col}, '')), '{{weight}}')"

    parts = [
        f"setweight(to_tsvector('{_TS_LANG}', coalesce({name!r}, '')), 'A')"
        if name
        else f"setweight(to_tsvector('{_TS_LANG}', coalesce(NULL::text, '')), 'A')",
        f"setweight(to_tsvector('{_TS_LANG}', coalesce({display_number!r}, '')), 'B')"
        if display_number
        else f"setweight(to_tsvector('{_TS_LANG}', coalesce(NULL::text, '')), 'B')",
        f"setweight(to_tsvector('{_TS_LANG}', coalesce({kind!r}, '')), 'C')"
        if kind
        else f"setweight(to_tsvector('{_TS_LANG}', coalesce(NULL::text, '')), 'C')",
        f"setweight(to_tsvector('{_TS_LANG}', coalesce({description!r}, '')), 'D')"
        if description
        else f"setweight(to_tsvector('{_TS_LANG}', coalesce(NULL::text, '')), 'D')",
    ]
    return " || ".join(parts)


class PostgresIndexBuilder:
    """Index builder that maintains PostgreSQL FTS tables (search_vertex, search_edge).

    Uses INSERT ... ON CONFLICT (id) DO UPDATE to upsert documents so re-indexing
    is idempotent. The text_vector column is populated via the weighted to_tsvector
    expression built by ``_tsvector_expr``.
    """

    def __init__(self):
        self.name = "postgres_indexer"

    def upsert_vertex(self, tenant_id: UUID, vertex_id: UUID, data: dict) -> None:
        """Upsert a vertex document into search_vertex.

        data keys: kind, name, description, classificationId, prefix, number,
                   displayNumber, revision, lifecycleState, releaseOn (date),
                   markedForDeletion (bool), solutionAttributes (dict),
                   tenantAttributes (dict)
        """
        kind = data.get("kind")
        name = data.get("name") or ""
        display = data.get("displayNumber") or ""
        description = data.get("description") or ""
        tsvec_sql = (
            f"setweight(to_tsvector('{_TS_LANG}', coalesce({name!r}, '')), 'A') || "
            f"setweight(to_tsvector('{_TS_LANG}', coalesce({display!r}, '')), 'B') || "
            f"setweight(to_tsvector('{_TS_LANG}', coalesce({kind!r}, '')), 'C') || "
            f"setweight(to_tsvector('{_TS_LANG}', coalesce({description!r}, '')), 'D')"
        )
        release_on = data.get("releaseOn")
        sql = text(f"""
            INSERT INTO plmiqdb.search_vertex
                (id, tenant_id, entity_type, kind, classification_id, prefix, number,
                 display_number, name, description, revision, lifecycle_state, release_on,
                 marked_for_deletion, solution_attributes, tenant_attributes, text_vector,
                 modified_on)
            VALUES
                (:id, :tenant_id, 'vertex', :kind, :classification_id, :prefix, :number,
                 :display_number, :name, :description, :revision, :lifecycle_state, :release_on,
                 :marked_for_deletion, :solution_attributes::jsonb, :tenant_attributes::jsonb,
                 ({tsvec_sql})::tsvector, NOW())
            ON CONFLICT (id) DO UPDATE SET
                kind               = EXCLUDED.kind,
                classification_id  = EXCLUDED.classification_id,
                prefix             = EXCLUDED.prefix,
                number             = EXCLUDED.number,
                display_number     = EXCLUDED.display_number,
                name               = EXCLUDED.name,
                description        = EXCLUDED.description,
                revision           = EXCLUDED.revision,
                lifecycle_state    = EXCLUDED.lifecycle_state,
                release_on         = EXCLUDED.release_on,
                marked_for_deletion = EXCLUDED.marked_for_deletion,
                solution_attributes = EXCLUDED.solution_attributes,
                tenant_attributes  = EXCLUDED.tenant_attributes,
                text_vector        = ({tsvec_sql})::tsvector,
                modified_on        = NOW()
        """)
        with db.tenant_session(tenant_id) as session:
            session.execute(sql, {
                "id": vertex_id,
                "tenant_id": tenant_id,
                "kind": kind,
                "classification_id": data.get("classificationId"),
                "prefix": data.get("prefix"),
                "number": data.get("number"),
                "display_number": display,
                "name": name,
                "description": description,
                "revision": data.get("revision"),
                "lifecycle_state": data.get("lifecycleState"),
                "release_on": release_on,
                "marked_for_deletion": bool(data.get("markedForDeletion")),
                "solution_attributes": data.get("solutionAttributes") or {},
                "tenant_attributes": data.get("tenantAttributes") or {},
            })
            session.commit()

    def upsert_edge(self, tenant_id: UUID, edge_id: UUID, data: dict) -> None:
        """Upsert an edge document into search_edge.

        data keys: kind, name, lifecycleState, effectiveFrom (date), effectiveTo (date),
                   sourceVertexId, sourceVertexKind, sourceDisplay, sourceName,
                   targetVertexId, targetVertexKind, targetDisplay, targetName,
                   annotation (dict), tenantAttributes (dict)
        """
        kind = data.get("kind") or ""
        name = data.get("name") or ""
        tsvec_sql = (
            f"setweight(to_tsvector('{_TS_LANG}', coalesce({name!r}, '')), 'A') || "
            f"setweight(to_tsvector('{_TS_LANG}', coalesce({kind!r}, '')), 'C')"
        )
        sql = text(f"""
            INSERT INTO plmiqdb.search_edge
                (id, tenant_id, entity_type, kind, name, lifecycle_state,
                 effective_from, effective_to,
                 source_vertex_id, source_vertex_kind, source_display, source_name,
                 target_vertex_id, target_vertex_kind, target_display, target_name,
                 annotation, tenant_attributes, text_vector, modified_on)
            VALUES
                (:id, :tenant_id, 'edge', :kind, :name, :lifecycle_state,
                 :effective_from, :effective_to,
                 :source_vertex_id, :source_vertex_kind, :source_display, :source_name,
                 :target_vertex_id, :target_vertex_kind, :target_display, :target_name,
                 :annotation::jsonb, :tenant_attributes::jsonb,
                 ({tsvec_sql})::tsvector, NOW())
            ON CONFLICT (id) DO UPDATE SET
                kind               = EXCLUDED.kind,
                name               = EXCLUDED.name,
                lifecycle_state    = EXCLUDED.lifecycle_state,
                effective_from     = EXCLUDED.effective_from,
                effective_to       = EXCLUDED.effective_to,
                source_vertex_id   = EXCLUDED.source_vertex_id,
                source_vertex_kind = EXCLUDED.source_vertex_kind,
                source_display     = EXCLUDED.source_display,
                source_name        = EXCLUDED.source_name,
                target_vertex_id   = EXCLUDED.target_vertex_id,
                target_vertex_kind = EXCLUDED.target_vertex_kind,
                target_display     = EXCLUDED.target_display,
                target_name        = EXCLUDED.target_name,
                annotation         = EXCLUDED.annotation,
                tenant_attributes  = EXCLUDED.tenant_attributes,
                text_vector        = ({tsvec_sql})::tsvector,
                modified_on        = NOW()
        """)
        with db.tenant_session(tenant_id) as session:
            session.execute(sql, {
                "id": edge_id,
                "tenant_id": tenant_id,
                "kind": kind,
                "name": name,
                "lifecycle_state": data.get("lifecycleState"),
                "effective_from": data.get("effectiveFrom"),
                "effective_to": data.get("effectiveTo"),
                "source_vertex_id": data.get("sourceVertexId"),
                "source_vertex_kind": data.get("sourceVertexKind"),
                "source_display": data.get("sourceDisplay"),
                "source_name": data.get("sourceName"),
                "target_vertex_id": data.get("targetVertexId"),
                "target_vertex_kind": data.get("targetVertexKind"),
                "target_display": data.get("targetDisplay"),
                "target_name": data.get("targetName"),
                "annotation": data.get("annotation") or {},
                "tenant_attributes": data.get("tenantAttributes") or {},
            })
            session.commit()

    def delete_vertex(self, tenant_id: UUID, vertex_id: UUID) -> None:
        """Hard-delete a vertex from search_vertex."""
        sql = text(
            "DELETE FROM plmiqdb.search_vertex WHERE id = :id AND tenant_id = :tenant_id"
        )
        with db.tenant_session(tenant_id) as session:
            session.execute(sql, {"id": vertex_id, "tenant_id": tenant_id})
            session.commit()

    def delete_edge(self, tenant_id: UUID, edge_id: UUID) -> None:
        """Hard-delete an edge from search_edge."""
        sql = text(
            "DELETE FROM plmiqdb.search_edge WHERE id = :id AND tenant_id = :tenant_id"
        )
        with db.tenant_session(tenant_id) as session:
            session.execute(sql, {"id": edge_id, "tenant_id": tenant_id})
            session.commit()

    def bulk_upsert_vertices(self, tenant_id: UUID, documents: list[dict]) -> dict:
        """Bulk upsert a list of vertex documents.

        Uses ON CONFLICT ... DO UPDATE per row so re-indexing is idempotent.
        Commits after all rows.
        """
        if not documents:
            return {"indexed": 0}
        for doc in documents:
            vid = doc.get("id") or doc.get("vertexId")
            if not vid:
                continue
            try:
                self.upsert_vertex(tenant_id, UUID(str(vid)), doc)
            except Exception as exc:
                logger.warning("pg_index.bulk_vertex.failed", extra={"id": str(vid), "error": str(exc)})
        return {"indexed": len(documents)}

    def bulk_upsert_edges(self, tenant_id: UUID, documents: list[dict]) -> dict:
        """Bulk upsert a list of edge documents."""
        if not documents:
            return {"indexed": 0}
        for doc in documents:
            eid = doc.get("id") or doc.get("edgeId")
            if not eid:
                continue
            try:
                self.upsert_edge(tenant_id, UUID(str(eid)), doc)
            except Exception as exc:
                logger.warning("pg_index.bulk_edge.failed", extra={"id": str(eid), "error": str(exc)})
        return {"indexed": len(documents)}

    def rebuild(self, tenant_id: UUID, vertices: list[dict], edges: list[dict]) -> None:
        """Replace all search documents for a tenant with fresh data.

        Deletes all existing search entries for the tenant, then bulk-upserts the
        new documents. This is the PG equivalent of a full ES re-index.
        """
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
        self.bulk_upsert_vertices(tenant_id, vertices)
        self.bulk_upsert_edges(tenant_id, edges)
        logger.info("pg_index.rebuild.done", extra={
            "tenant": str(tenant_id),
            "vertices": len(vertices),
            "edges": len(edges),
        })

    def health(self) -> dict:
        """Return overall health of the PG search indexer."""
        try:
            with db.admin_session() as session:
                session.execute(text("SELECT 1"))
            return {"platform": "POSTGRES", "indexer": "ok"}
        except Exception as exc:
            logger.error("postgres_index.health.failed", extra={"error": str(exc)})
            return {"platform": "POSTGRES", "indexer": "error", "detail": str(exc)}


#: Singleton instance — returned by search_service_factory when SEARCH_PLATFORM=POSTGRES.
pg_indexer = PostgresIndexBuilder()
