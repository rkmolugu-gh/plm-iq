"""GraphQueryService - traversals over foundation_edge using recursive CTEs.

All queries filter on tenant_id explicitly (defense in depth alongside RLS)
and bound traversal depth with a visited-path array to survive cycles.
Returned rows use camelCase keys, ready for the API layer.

Why a class
-----------
The three public traversals share one bounded-walk engine (_traverse) and
one SQL template; grouping them documents that relationship and gives future
query types (impact paths, genealogy, configuration scopes) an obvious home.

How to extend (future scenarios)
--------------------------------
* New traversal -> add a method delegating to _traverse with anchor/opposite
  swapped; depth/kind limits stay caller-controlled.
* Performance work -> tune _WALK_SQL once; all traversals benefit.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import enums

logger = logging.getLogger(__name__)

_DEFAULT_TRAVERSAL_KINDS = (
    enums.EdgeKind.BOM,
    enums.EdgeKind.CONTAINS,
    enums.EdgeKind.USES,
)

_WALK_SQL = """
WITH RECURSIVE walk AS (
    SELECT e.{anchor} AS vertex_id, ARRAY[e.{anchor}] AS path, 1 AS depth
    FROM plmiqdb.foundation_edge e
    WHERE e.{opposite} = :root_id
      AND e.tenant_id = :tenant_id
      AND e.kind::text = ANY(:kinds)
      AND e.lifecycle_state <> 'inactive'
    UNION
    SELECT e.{anchor}, walk.path || e.{anchor}, walk.depth + 1
    FROM plmiqdb.foundation_edge e
    JOIN walk ON e.{opposite} = walk.vertex_id
    WHERE e.tenant_id = :tenant_id
      AND e.kind::text = ANY(:kinds)
      AND e.lifecycle_state <> 'inactive'
      AND NOT e.{anchor} = ANY(walk.path)
      AND walk.depth < :max_depth
)
SELECT * FROM (
    SELECT DISTINCT ON (v.id)
        v.id AS "id", v.kind::text AS "kind", v.prefix AS "prefix",
        v.number AS "number", v.name AS "name", v.revision AS "revision",
        v.lifecycle_state::text AS "lifecycleState", w.depth AS "depth"
    FROM walk w
    JOIN plmiqdb.foundation_vertex v ON v.id = w.vertex_id
    ORDER BY v.id, w.depth
) q
ORDER BY q."depth", q."number"
LIMIT :limit
"""

_NEIGHBOR_SQL = """
SELECT e.kind::text AS "edgeKind",
       e.name AS "edgeName",
       e.lifecycle_state::text AS "edgeState",
       CASE WHEN e.source_vertex_id = :vertex_id THEN 'outgoing' ELSE 'incoming' END AS "direction",
       v.id AS "id", v.kind::text AS "kind", v.prefix AS "prefix",
       v.number AS "number", v.name AS "name", v.revision AS "revision",
       v.lifecycle_state::text AS "lifecycleState"
FROM plmiqdb.foundation_edge e
JOIN plmiqdb.foundation_vertex v
  ON v.id = CASE WHEN e.source_vertex_id = :vertex_id THEN e.target_vertex_id ELSE e.source_vertex_id END
WHERE (e.source_vertex_id = :vertex_id OR e.target_vertex_id = :vertex_id)
  AND e.lifecycle_state <> 'inactive'{direction_clause}
ORDER BY v."number"
LIMIT :limit
"""


_BOM_TREE_SQL = """
WITH RECURSIVE bom AS (
    SELECT e.id AS edge_id, e.source_vertex_id AS parent_vertex_id,
           e.target_vertex_id AS vertex_id, e.name AS edge_name,
           e.lifecycle_state::text AS edge_state, e.annotation AS annotation,
           e.version AS edge_version, 1 AS depth,
           ARRAY[e.target_vertex_id] AS path
    FROM plmiqdb.foundation_edge e
    WHERE e.source_vertex_id = :root_id
      AND e.tenant_id = :tenant_id
      AND e.kind::text = 'BOM'
      AND e.lifecycle_state::text <> 'inactive'
    UNION ALL
    SELECT e.id, e.source_vertex_id, e.target_vertex_id, e.name,
           e.lifecycle_state::text, e.annotation, e.version, bom.depth + 1,
           bom.path || e.target_vertex_id
    FROM plmiqdb.foundation_edge e
    JOIN bom ON e.source_vertex_id = bom.vertex_id
    WHERE e.tenant_id = :tenant_id
      AND e.kind::text = 'BOM'
      AND e.lifecycle_state::text <> 'inactive'
      AND NOT e.target_vertex_id = ANY(bom.path)
      AND bom.depth < :max_depth
)
SELECT b.edge_id AS "edgeId", b.parent_vertex_id AS "parentVertexId",
       b.vertex_id AS "vertexId", b.depth AS "depth",
       b.edge_name AS "edgeName", b.edge_state AS "edgeState",
       b.edge_version AS "edgeVersion", b.annotation AS "annotation",
       v.prefix AS "prefix", v.number AS "number", v.name AS "name",
       v.revision AS "revision", v.lifecycle_state::text AS "lifecycleState"
FROM bom b
JOIN plmiqdb.foundation_vertex v ON v.id = b.vertex_id
ORDER BY b.path
LIMIT :limit
"""


class GraphQueryService:
    def neighbors(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        vertex_id: UUID,
        direction: str = "both",
        limit: int = 50,
    ) -> list[dict]:
        if direction not in {"both", "incoming", "outgoing"}:
            raise ValueError(f"direction must be 'both', 'incoming', or 'outgoing', got '{direction}'")
        clause = ""
        if direction == "outgoing":
            clause = " AND e.source_vertex_id = :vertex_id"
        elif direction == "incoming":
            clause = " AND e.target_vertex_id = :vertex_id"
        rows = session.execute(
            text(_NEIGHBOR_SQL.format(direction_clause=clause)),
            {"vertex_id": str(vertex_id), "limit": min(max(limit, 1), 500)},
        ).all()
        return [dict(r._mapping) for r in rows]

    def where_used(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        root_id: UUID,
        edge_kinds: tuple[enums.EdgeKind, ...] | None = None,
        max_depth: int = 4,
        limit: int = 200,
    ) -> list[dict]:
        """Vertices that (transitively) consume the root through the given edge kinds."""
        return self._traverse(
            session,
            anchor="source_vertex_id",
            opposite="target_vertex_id",
            tenant_id=tenant_id,
            root_id=root_id,
            edge_kinds=edge_kinds or _DEFAULT_TRAVERSAL_KINDS,
            max_depth=max_depth,
            limit=limit,
        )

    def impact(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        root_id: UUID,
        edge_kinds: tuple[enums.EdgeKind, ...] | None = None,
        max_depth: int = 4,
        limit: int = 200,
    ) -> list[dict]:
        """Downstream vertices affected by a change to the root."""
        return self._traverse(
            session,
            anchor="target_vertex_id",
            opposite="source_vertex_id",
            tenant_id=tenant_id,
            root_id=root_id,
            edge_kinds=edge_kinds or _DEFAULT_TRAVERSAL_KINDS,
            max_depth=max_depth,
            limit=limit,
        )

    def bom_tree(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        root_id: UUID,
        max_depth: int = 12,
        limit: int = 1000,
    ) -> list[dict]:
        """Flatten the BOM (kind='BOM') structure rooted at ``root_id``.

        Each row is one parent->child relationship (edge), not a vertex, so a
        multi-use child appears once per place it is used - the flattened
        table a BOM editor needs. ``depth`` starts at 1 for the root's direct
        children; the caller renders the root itself as a separate header
        row. Carries the edge id/version/annotation so the gateway can update
        or delete the exact relationship a row represents.
        """
        rows = session.execute(
            text(_BOM_TREE_SQL),
            {
                "root_id": str(root_id),
                "tenant_id": str(tenant_id),
                "max_depth": max(1, max_depth),
                "limit": min(max(limit, 1), 5000),
            },
        ).all()
        return [dict(r._mapping) for r in rows]

    def _traverse(
        self,
        session: Session,
        *,
        anchor: str,
        opposite: str,
        tenant_id: UUID,
        root_id: UUID,
        edge_kinds: tuple[enums.EdgeKind, ...],
        max_depth: int,
        limit: int,
    ) -> list[dict]:
        params = {
            "root_id": str(root_id),
            "tenant_id": str(tenant_id),
            "kinds": [kind.value for kind in edge_kinds],
            "max_depth": max(1, max_depth),
            "limit": min(max(limit, 1), 1000),
        }
        sql = _WALK_SQL.format(anchor=anchor, opposite=opposite)
        rows = session.execute(text(sql), params).all()
        logger.debug("graph.traversal", extra={
            "root": str(root_id), "direction": anchor, "rows": len(rows), "max_depth": max_depth,
        })
        return [dict(r._mapping) for r in rows]


#: Shared singleton - stateless query engine.
queries = GraphQueryService()
