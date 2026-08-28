"""Tools service providing assistant tooling for the workspace.

Provides comprehensive graph theory based tools for interacting with the
workspace data model: vertices, edges, edge annotations, and edge rules.

The service exposes two surfaces the assistant needs:

* ``TOOL_SCHEMAS`` - OpenAI-style function schemas handed to the LLM so it
  knows what tools exist and how to call them.
* ``execute(name, args, *, session, tenant_id)`` - dispatches a tool call the
  model requested, returning a JSON string the assistant feeds back as a
  ``tool`` message. Adding a tool = add a method + a schema entry; the ReAct
  loop in the assistant stays unchanged.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from .document_service import documents
from .edge_service import edges
from .errors import ServiceError
from .graph_rule_service import rules as graph_rules
from .rule_engine import validator
from .vertex_service import vertices

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 5

# -- Document tools -----------------------------------------------------------

_LIST_DOCUMENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_documents",
        "description": (
            "List the most recently created documents in this tenant, returning "
            "each document\'s id, prefix-number, revision, kind, name, lifecycle "
            "state, and description. Use this to discover documents before a "
            "follow-up query."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of documents to return (default 5).",
                },
            },
            "required": [],
        },
    },
}

# -- Vertex tools -------------------------------------------------------------

_LIST_VERTICES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_vertices",
        "description": (
            "List all vertices in the tenant workspace. Returns each vertex\'s "
            "id, label (prefix-number), revision, kind, name, lifecycle state, "
            "and description. Supports filtering by kind and lifecycle state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["Vertex", "Part", "Document", "EC"],
                    "description": "Filter by vertex kind.",
                },
                "lifecycle_state": {
                    "type": "string",
                    "enum": ["draft", "in_review", "approved", "released", "superseded", "obsolete"],
                    "description": "Filter by lifecycle state.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of vertices to return (default 50).",
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of vertices to skip for pagination (default 0).",
                },
            },
            "required": [],
        },
    },
}

_GET_VERTEX_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_vertex",
        "description": (
            "Get a single vertex by its internal ID. Returns full details including "
            "all attributes, lifecycle state, and metadata."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vertex_id": {
                    "type": "string",
                    "description": "The UUID of the vertex to retrieve.",
                },
            },
            "required": ["vertex_id"],
        },
    },
}

_CREATE_VERTEX_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_vertex",
        "description": (
            "Create a new vertex in the workspace. Specify kind (Part, Document, EC), "
            "number, name, and optional attributes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["Part", "Document", "EC"],
                    "description": "The vertex kind.",
                },
                "number": {
                    "type": "string",
                    "description": "The unique number for this vertex.",
                },
                "name": {
                    "type": "string",
                    "description": "The display name.",
                },
                "prefix": {
                    "type": "string",
                    "description": "The prefix (default V).",
                },
                "revision": {
                    "type": "string",
                    "description": "The revision identifier (default A).",
                },
                "description": {
                    "type": "string",
                    "description": "Description text.",
                },
                "solution_attributes": {
                    "type": "object",
                    "description": "Key-value attributes specific to the vertex type.",
                },
                "tenant_attributes": {
                    "type": "object",
                    "description": "Tenant-specific key-value attributes.",
                },
            },
            "required": ["kind", "number", "name"],
        },
    },
}

_UPDATE_VERTEX_SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_vertex",
        "description": (
            "Update an existing vertex. Requires the vertex version for optimistic locking. "
            "Only specified fields are updated. Lifecycle transitions follow allowed paths."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vertex_id": {
                    "type": "string",
                    "description": "The UUID of the vertex to update.",
                },
                "version": {
                    "type": "integer",
                    "description": "Current version number for optimistic locking.",
                },
                "name": {"type": "string", "description": "New name."},
                "description": {"type": "string", "description": "New description."},
                "revision": {"type": "string", "description": "New revision."},
                "lifecycle_state": {
                    "type": "string",
                    "description": "New lifecycle state.",
                },
                "release_on": {
                    "type": "string",
                    "description": "Release date (YYYY-MM-DD).",
                },
                "solution_attributes": {
                    "type": "object",
                    "description": "Updated solution attributes.",
                },
                "tenant_attributes": {
                    "type": "object",
                    "description": "Updated tenant attributes.",
                },
            },
            "required": ["vertex_id", "version"],
        },
    },
}

_DELETE_VERTEX_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delete_vertex",
        "description": (
            "Soft-delete a vertex. Sets marked_for_deletion flag. "
            "Released vertices cannot be deleted directly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vertex_id": {
                    "type": "string",
                    "description": "The UUID of the vertex to delete.",
                },
            },
            "required": ["vertex_id"],
        },
    },
}

# -- Edge tools ----------------------------------------------------------------

_LIST_EDGES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_edges",
        "description": (
            "List edges (relationships) in the workspace. Returns kind, name, "
            "source/target labels, lifecycle state, effectivity window, and annotation. "
            "Supports filtering by source/target vertex and edge kind."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Filter by edge kind (BOM, REFDOCS, USES, etc.).",
                },
                "lifecycle_state": {
                    "type": "string",
                    "description": "Filter by lifecycle state.",
                },
                "source_vertex_id": {
                    "type": "string",
                    "description": "Filter by source vertex UUID.",
                },
                "target_vertex_id": {
                    "type": "string",
                    "description": "Filter by target vertex UUID.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of edges to return (default 50).",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination (default 0).",
                },
            },
            "required": [],
        },
    },
}

_GET_EDGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_edge",
        "description": (
            "Get a single edge by its internal ID. Returns full details including "
            "kind, name, source/target info, lifecycle state, effectivity, and annotation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edge_id": {
                    "type": "string",
                    "description": "The UUID of the edge to retrieve.",
                },
            },
            "required": ["edge_id"],
        },
    },
}

_CREATE_EDGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_edge",
        "description": (
            "Create a new relationship (edge) between two vertices. The edge kind must "
            "be governed by a graph rule. Specifies source/target vertex IDs, kind, name, "
            "and optional annotation attributes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "description": "Edge kind (BOM, REFDOCS, USES, AFFECTS, SUPERSEDES, etc.).",
                },
                "name": {
                    "type": "string",
                    "description": "Display name for this relationship.",
                },
                "source_vertex_id": {
                    "type": "string",
                    "description": "UUID of the source vertex.",
                },
                "target_vertex_id": {
                    "type": "string",
                    "description": "UUID of the target vertex.",
                },
                "annotation": {
                    "type": "object",
                    "description": "Key-value annotation attributes required by the governing rule.",
                },
                "effective_from": {
                    "type": "string",
                    "description": "Start of effectivity window (YYYY-MM-DD).",
                },
                "effective_to": {
                    "type": "string",
                    "description": "End of effectivity window (YYYY-MM-DD).",
                },
            },
            "required": ["kind", "name", "source_vertex_id", "target_vertex_id"],
        },
    },
}

_UPDATE_EDGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "update_edge",
        "description": (
            "Update an existing edge. Requires version for optimistic locking. "
            "Can update name, lifecycle state, effectivity window, and annotation/attributes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edge_id": {
                    "type": "string",
                    "description": "The UUID of the edge to update.",
                },
                "version": {
                    "type": "integer",
                    "description": "Current version number for optimistic locking.",
                },
                "name": {"type": "string", "description": "New name."},
                "lifecycle_state": {
                    "type": "string",
                    "description": "New lifecycle state.",
                },
                "effective_from": {
                    "type": "string",
                    "description": "New effective from date.",
                },
                "effective_to": {
                    "type": "string",
                    "description": "New effective to date.",
                },
                "annotation": {
                    "type": "object",
                    "description": "Updated annotation attributes.",
                },
                "tenant_attributes": {
                    "type": "object",
                    "description": "Updated tenant attributes.",
                },
            },
            "required": ["edge_id", "version"],
        },
    },
}

_DELETE_EDGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delete_edge",
        "description": (
            "Delete an edge relationship. Removes the edge row permanently."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edge_id": {
                    "type": "string",
                    "description": "The UUID of the edge to delete.",
                },
            },
            "required": ["edge_id"],
        },
    },
}

# -- Edge annotation tools ----------------------------------------------------

_GET_EDGE_ANNOTATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_edge_annotation",
        "description": (
            "Retrieve the annotation attributes stored on a specific edge. "
            "Returns key-value pairs like quantity, unitOfMeasure, referenceCategory, etc."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edge_id": {
                    "type": "string",
                    "description": "The UUID of the edge.",
                },
            },
            "required": ["edge_id"],
        },
    },
}

_SET_EDGE_ANNOTATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "set_edge_annotation",
        "description": (
            "Set or update annotation attributes on an edge. Annotation is merged "
            "with existing attributes. Required attributes from the governing rule "
            "must be present after the update."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edge_id": {
                    "type": "string",
                    "description": "The UUID of the edge.",
                },
                "version": {
                    "type": "integer",
                    "description": "Current version for optimistic locking.",
                },
                "annotation": {
                    "type": "object",
                    "description": "Key-value annotation attributes to set/merge.",
                },
            },
            "required": ["edge_id", "version", "annotation"],
        },
    },
}

# -- Graph rule tools ---------------------------------------------------------

_LIST_GRAPH_RULES_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_graph_rules",
        "description": (
            "List all graph rules that govern edge creation. Rules define which edge "
            "kinds are allowed between vertex kinds, cardinality constraints, required "
            "attributes, and lifecycle state restrictions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["platform", "edition", "tenant"],
                    "description": "Filter by rule scope.",
                },
                "edge_kind": {
                    "type": "string",
                    "description": "Filter by edge kind.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of rules to return (default 50).",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination (default 0).",
                },
            },
            "required": [],
        },
    },
}

_GET_GRAPH_RULE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_graph_rule",
        "description": (
            "Get a single graph rule by its ID. Returns full rule details including "
            "cardinality, participation, lifecycle states, and required attributes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "rule_id": {
                    "type": "string",
                    "description": "The UUID of the graph rule.",
                },
            },
            "required": ["rule_id"],
        },
    },
}

_RESOLVE_RULE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "resolve_governing_rule",
        "description": (
            "Resolve which graph rule governs a given edge pattern (kind + source kind + target kind). "
            "Returns the most specific matching rule based on precedence: tenant > edition > platform."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edge_kind": {
                    "type": "string",
                    "description": "Edge kind (e.g., BOM, REFDOCS).",
                },
                "source_kind": {
                    "type": "string",
                    "description": "Source vertex kind (e.g., Part, Document).",
                },
                "target_kind": {
                    "type": "string",
                    "description": "Target vertex kind (e.g., Part, Document).",
                },
            },
            "required": ["edge_kind", "source_kind", "target_kind"],
        },
    },
}

# -- Graph analysis tools -----------------------------------------------------

_NEIGHBORS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_neighbors",
        "description": (
            "Find all neighboring vertices connected to a given vertex through edges. "
            "Returns outgoing and incoming neighbors with their connecting edge kinds."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vertex_id": {
                    "type": "string",
                    "description": "The UUID of the vertex to find neighbors for.",
                },
            },
            "required": ["vertex_id"],
        },
    },
}

_FIND_PATHS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_paths",
        "description": (
            "Find paths between two vertices up to a specified depth. "
            "Returns sequence of vertex labels connected by edge kinds."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "Starting vertex UUID.",
                },
                "target_id": {
                    "type": "string",
                    "description": "Ending vertex UUID.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum path length to search (default 3).",
                },
            },
            "required": ["source_id", "target_id"],
        },
    },
}

_GRAPH_STATS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_graph_stats",
        "description": (
            "Get summary statistics about the workspace graph: vertex counts by kind, "
            "edge counts by kind, and connectivity metrics."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

_CHECK_RULE_COMPLIANCE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "check_rule_compliance",
        "description": (
            "Check whether a proposed edge would comply with all governing graph rules. "
            "Validates kind compatibility, lifecycle states, required attributes, and duplicate policy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edge_kind": {
                    "type": "string",
                    "description": "Proposed edge kind.",
                },
                "source_kind": {
                    "type": "string",
                    "description": "Source vertex kind.",
                },
                "target_kind": {
                    "type": "string",
                    "description": "Target vertex kind.",
                },
                "source_lifecycle_state": {
                    "type": "string",
                    "description": "Source vertex lifecycle state.",
                },
                "target_lifecycle_state": {
                    "type": "string",
                    "description": "Target vertex lifecycle state.",
                },
                "annotation": {
                    "type": "object",
                    "description": "Proposed annotation attributes.",
                },
            },
            "required": ["edge_kind", "source_kind", "target_kind"],
        },
    },
}

#: Schemas exposed to the LLM. Extend here when adding tools.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    _LIST_DOCUMENTS_SCHEMA,
    _LIST_VERTICES_SCHEMA,
    _GET_VERTEX_SCHEMA,
    _CREATE_VERTEX_SCHEMA,
    _UPDATE_VERTEX_SCHEMA,
    _DELETE_VERTEX_SCHEMA,
    _LIST_EDGES_SCHEMA,
    _GET_EDGE_SCHEMA,
    _CREATE_EDGE_SCHEMA,
    _UPDATE_EDGE_SCHEMA,
    _DELETE_EDGE_SCHEMA,
    _GET_EDGE_ANNOTATION_SCHEMA,
    _SET_EDGE_ANNOTATION_SCHEMA,
    _LIST_GRAPH_RULES_SCHEMA,
    _GET_GRAPH_RULE_SCHEMA,
    _RESOLVE_RULE_SCHEMA,
    _NEIGHBORS_SCHEMA,
    _FIND_PATHS_SCHEMA,
    _GRAPH_STATS_SCHEMA,
    _CHECK_RULE_COMPLIANCE_SCHEMA,
]


class ToolService:
    """Tool service providing assistant-accessible operations."""

    # -- Documents ---------------------------------------------------------------

    def list_documents(
        self,
        session: Session,
        tenant_id: UUID,
        *,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """List the last N documents created in the tenant."""
        try:
            page = documents.list(session, tenant_id, limit=limit)
            items = []
            for v in page.items:
                row = v.model_dump(mode="json")
                items.append({
                    "id": row["id"],
                    "prefix": row["prefix"],
                    "number": row["number"],
                    "revision": row["revision"],
                    "kind": row["kind"],
                    "name": row["name"],
                    "lifecycle_state": row["lifecycle_state"],
                    "description": row.get("description") or "",
                    "release_on": row.get("release_on") or "",
                    "version": row.get("version") or "",
                })
            return {
                "total": page.total,
                "limit": limit,
                "documents": items,
            }
        except Exception as exc:
            logger.warning("tool.list_documents.error", extra={"tenant": str(tenant_id)}, exc_info=exc)
            raise ServiceError(f"Failed to list documents: {exc}") from exc

    # -- Vertex CRUD -------------------------------------------------------------

    def list_vertices(
        self,
        session: Session,
        tenant_id: UUID,
        *,
        kind: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List vertices with optional filtering."""
        try:
            from .enums import LifecycleState, VertexKind
            kind_filter = None
            if kind:
                try:
                    kind_filter = VertexKind(kind)
                except ValueError:
                    pass
            lifecycle_filter = None
            if lifecycle_state:
                try:
                    lifecycle_filter = LifecycleState(lifecycle_state)
                except ValueError:
                    pass
            page = vertices.list(
                session, tenant_id,
                kinds=[kind_filter] if kind_filter else None,
                lifecycle_states=[lifecycle_filter] if lifecycle_filter else None,
                limit=limit, offset=offset,
            )
            items = []
            for v in page.items:
                row = v.model_dump(mode="json")
                items.append({
                    "id": str(row["id"]),
                    "label": f"{row['prefix']}-{row['number']}" + (f"/{row['revision']}" if row.get("revision") else ""),
                    "prefix": row["prefix"],
                    "number": row["number"],
                    "revision": row["revision"],
                    "kind": row["kind"].value if hasattr(row["kind"], "value") else row["kind"],
                    "name": row["name"],
                    "lifecycle_state": row["lifecycle_state"].value if hasattr(row["lifecycle_state"], "value") else row["lifecycle_state"],
                    "description": row.get("description") or "",
                    "solution_attributes": row.get("solution_attributes") or {},
                    "tenant_attributes": row.get("tenant_attributes") or {},
                    "version": row["version"],
                })
            return {"total": page.total, "limit": limit, "offset": offset, "vertices": items}
        except Exception as exc:
            logger.warning("tool.list_vertices.error", extra={"tenant": str(tenant_id)}, exc_info=exc)
            raise ServiceError(f"Failed to list vertices: {exc}") from exc

    def get_vertex(self, session: Session, tenant_id: UUID, vertex_id: str) -> dict[str, Any]:
        """Get a single vertex by ID."""
        try:
            v = vertices.get(session, tenant_id, UUID(vertex_id))
            return {
                "id": str(v["id"]),
                "label": f"{v['prefix']}-{v['number']}" + (f"/{v['revision']}" if v.get("revision") else ""),
                "prefix": v["prefix"],
                "number": v["number"],
                "revision": v["revision"],
                "kind": v["kind"].value if hasattr(v["kind"], "value") else v["kind"],
                "name": v["name"],
                "lifecycle_state": v["lifecycle_state"].value if hasattr(v["lifecycle_state"], "value") else v["lifecycle_state"],
                "description": v.get("description") or "",
                "release_on": v.get("release_on"),
                "solution_attributes": v.get("solution_attributes") or {},
                "tenant_attributes": v.get("tenant_attributes") or {},
                "version": v["version"],
                "created_by": v["created_by"],
                "created_on": str(v["created_on"]) if v.get("created_on") else "",
                "modified_by": v["modified_by"],
                "modified_on": str(v["modified_on"]) if v.get("modified_on") else "",
            }
        except Exception as exc:
            logger.warning("tool.get_vertex.error", extra={"tenant": str(tenant_id), "vertex_id": vertex_id}, exc_info=exc)
            raise ServiceError(f"Failed to get vertex {vertex_id}: {exc}") from exc

    def create_vertex(
        self, session: Session, tenant_id: UUID, actor: str,
        kind: str, number: str, name: str,
        prefix: str = "V", revision: str = "A",
        description: str = "",
        solution_attributes: dict | None = None,
        tenant_attributes: dict | None = None,
    ) -> dict[str, Any]:
        """Create a new vertex."""
        try:
            from .schemas import VertexCreate
            from .enums import EditionId, VertexKind
            vc = VertexCreate(
                edition_id=EditionId.FOUNDATION,
                kind=VertexKind(kind),
                number=number, name=name, prefix=prefix,
                revision=revision, description=description,
                solution_attributes=solution_attributes or {},
                tenant_attributes=tenant_attributes or {},
            )
            v = vertices.create(session, tenant_id, vc, actor)
            return {"status": "created", "vertex": self._vertex_out(v)}
        except Exception as exc:
            logger.warning("tool.create_vertex.error", extra={"tenant": str(tenant_id)}, exc_info=exc)
            raise ServiceError(f"Failed to create vertex: {exc}") from exc

    def update_vertex(
        self, session: Session, tenant_id: UUID, actor: str,
        vertex_id: str, version: int,
        name: str | None = None, description: str | None = None,
        revision: str | None = None, lifecycle_state: str | None = None,
        release_on: str | None = None,
        solution_attributes: dict | None = None,
        tenant_attributes: dict | None = None,
    ) -> dict[str, Any]:
        """Update a vertex."""
        try:
            from .schemas import VertexUpdate
            from .enums import LifecycleState
            changes = {}
            if name is not None:
                changes["name"] = name
            if description is not None:
                changes["description"] = description
            if revision is not None:
                changes["revision"] = revision
            if lifecycle_state is not None:
                changes["lifecycle_state"] = LifecycleState(lifecycle_state)
            if release_on is not None:
                changes["release_on"] = release_on
            if solution_attributes is not None:
                changes["solution_attributes"] = solution_attributes
            if tenant_attributes is not None:
                changes["tenant_attributes"] = tenant_attributes
            vu = VertexUpdate(version=version, **changes)
            v = vertices.update(session, tenant_id, UUID(vertex_id), vu, actor)
            return {"status": "updated", "vertex": self._vertex_out(v)}
        except Exception as exc:
            logger.warning("tool.update_vertex.error", extra={"tenant": str(tenant_id), "vertex_id": vertex_id}, exc_info=exc)
            raise ServiceError(f"Failed to update vertex {vertex_id}: {exc}") from exc

    def delete_vertex(self, session: Session, tenant_id: UUID, actor: str, vertex_id: str) -> dict[str, Any]:
        """Soft-delete a vertex."""
        try:
            vertices.delete(session, tenant_id, UUID(vertex_id), actor=actor)
            return {"status": "deleted", "vertex_id": vertex_id}
        except Exception as exc:
            logger.warning("tool.delete_vertex.error", extra={"tenant": str(tenant_id), "vertex_id": vertex_id}, exc_info=exc)
            raise ServiceError(f"Failed to delete vertex {vertex_id}: {exc}") from exc

    @staticmethod
    def _vertex_out(v) -> dict:
        row = v.model_dump(mode="json") if hasattr(v, "model_dump") else dict(v)
        return {
            "id": str(row["id"]),
            "label": f"{row['prefix']}-{row['number']}" + (f"/{row['revision']}" if row.get("revision") else ""),
            "kind": row["kind"].value if hasattr(row["kind"], "value") else row["kind"],
            "name": row["name"],
            "lifecycle_state": row["lifecycle_state"].value if hasattr(row["lifecycle_state"], "value") else row["lifecycle_state"],
        }

    # -- Edge CRUD ---------------------------------------------------------------

    def list_edges(
        self,
        session: Session,
        tenant_id: UUID,
        *,
        kind: str | None = None,
        lifecycle_state: str | None = None,
        source_vertex_id: str | None = None,
        target_vertex_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List edges with optional filtering."""
        try:
            from .enums import EdgeKind, EdgeState
            kind_filter = None
            if kind:
                try:
                    kind_filter = EdgeKind(kind)
                except ValueError:
                    pass
            lifecycle_filter = None
            if lifecycle_state:
                try:
                    lifecycle_filter = EdgeState(lifecycle_state)
                except ValueError:
                    pass
            src_id = UUID(source_vertex_id) if source_vertex_id else None
            tgt_id = UUID(target_vertex_id) if target_vertex_id else None
            page = edges.list(
                session, tenant_id,
                kinds=[kind_filter] if kind_filter else None,
                lifecycle_states=[lifecycle_filter] if lifecycle_filter else None,
                source_vertex_id=src_id, target_vertex_id=tgt_id,
                limit=limit, offset=offset,
            )
            items = []
            for e in page.items:
                row = e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
                items.append({
                    "id": str(row["id"]),
                    "kind": row["kind"].value if hasattr(row["kind"], "value") else row["kind"],
                    "name": row["name"],
                    "source_vertex_id": str(row["source_vertex_id"]),
                    "target_vertex_id": str(row["target_vertex_id"]),
                    "source_label": row.get("source_label", ""),
                    "target_label": row.get("target_label", ""),
                    "lifecycle_state": row["lifecycle_state"].value if hasattr(row["lifecycle_state"], "value") else row["lifecycle_state"],
                    "effective_from": str(row["effective_from"]) if row.get("effective_from") else "",
                    "effective_to": str(row["effective_to"]) if row.get("effective_to") else "",
                    "annotation": row.get("annotation") or {},
                    "version": row["version"],
                })
            return {"total": page.total, "limit": limit, "offset": offset, "edges": items}
        except Exception as exc:
            logger.warning("tool.list_edges.error", extra={"tenant": str(tenant_id)}, exc_info=exc)
            raise ServiceError(f"Failed to list edges: {exc}") from exc

    def get_edge(self, session: Session, tenant_id: UUID, edge_id: str) -> dict[str, Any]:
        """Get a single edge by ID."""
        try:
            e = edges.get(session, tenant_id, UUID(edge_id))
            return {
                "id": str(e["id"]),
                "kind": e["kind"].value if hasattr(e["kind"], "value") else e["kind"],
                "name": e["name"],
                "source_vertex_id": str(e["source_vertex_id"]),
                "target_vertex_id": str(e["target_vertex_id"]),
                "source_label": e.get("source_label", ""),
                "target_label": e.get("target_label", ""),
                "lifecycle_state": e["lifecycle_state"].value if hasattr(e["lifecycle_state"], "value") else e["lifecycle_state"],
                "effective_from": str(e["effective_from"]) if e.get("effective_from") else "",
                "effective_to": str(e["effective_to"]) if e.get("effective_to") else "",
                "annotation": e.get("annotation") or {},
                "version": e["version"],
            }
        except Exception as exc:
            logger.warning("tool.get_edge.error", extra={"tenant": str(tenant_id), "edge_id": edge_id}, exc_info=exc)
            raise ServiceError(f"Failed to get edge {edge_id}: {exc}") from exc

    def create_edge(
        self, session: Session, tenant_id: UUID, actor: str,
        kind: str, name: str,
        source_vertex_id: str, target_vertex_id: str,
        annotation: dict | None = None,
        effective_from: str | None = None,
        effective_to: str | None = None,
    ) -> dict[str, Any]:
        """Create a new edge relationship."""
        try:
            from .schemas import EdgeCreate
            from .enums import EdgeKind, EditionId
            from datetime import date
            ef = date.fromisoformat(effective_from) if effective_from else None
            et = date.fromisoformat(effective_to) if effective_to else None
            ec = EdgeCreate(
                edition_id=EditionId.FOUNDATION,
                kind=EdgeKind(kind), name=name,
                source_vertex_id=UUID(source_vertex_id),
                target_vertex_id=UUID(target_vertex_id),
                annotation=annotation or {},
                effective_from=ef, effective_to=et,
            )
            e = edges.create(session, tenant_id, ec, actor)
            return {"status": "created", "edge": self._edge_out(e)}
        except Exception as exc:
            logger.warning("tool.create_edge.error", extra={"tenant": str(tenant_id)}, exc_info=exc)
            raise ServiceError(f"Failed to create edge: {exc}") from exc

    def update_edge(
        self, session: Session, tenant_id: UUID, actor: str,
        edge_id: str, version: int,
        name: str | None = None, lifecycle_state: str | None = None,
        effective_from: str | None = None, effective_to: str | None = None,
        annotation: dict | None = None,
        tenant_attributes: dict | None = None,
    ) -> dict[str, Any]:
        """Update an edge."""
        try:
            from .schemas import EdgeUpdate
            from .enums import EdgeState
            from datetime import date
            changes = {}
            if name is not None:
                changes["name"] = name
            if lifecycle_state is not None:
                changes["lifecycle_state"] = EdgeState(lifecycle_state)
            if effective_from is not None:
                changes["effective_from"] = date.fromisoformat(effective_from)
            if effective_to is not None:
                changes["effective_to"] = date.fromisoformat(effective_to)
            if annotation is not None:
                changes["annotation"] = annotation
            if tenant_attributes is not None:
                changes["tenant_attributes"] = tenant_attributes
            eu = EdgeUpdate(version=version, **changes)
            e = edges.update(session, tenant_id, UUID(edge_id), eu, actor)
            return {"status": "updated", "edge": self._edge_out(e)}
        except Exception as exc:
            logger.warning("tool.update_edge.error", extra={"tenant": str(tenant_id), "edge_id": edge_id}, exc_info=exc)
            raise ServiceError(f"Failed to update edge {edge_id}: {exc}") from exc

    def delete_edge(self, session: Session, tenant_id: UUID, actor: str, edge_id: str) -> dict[str, Any]:
        """Delete an edge."""
        try:
            edges.delete(session, tenant_id, UUID(edge_id), actor=actor)
            return {"status": "deleted", "edge_id": edge_id}
        except Exception as exc:
            logger.warning("tool.delete_edge.error", extra={"tenant": str(tenant_id), "edge_id": edge_id}, exc_info=exc)
            raise ServiceError(f"Failed to delete edge {edge_id}: {exc}") from exc

    @staticmethod
    def _edge_out(e) -> dict:
        row = e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
        return {
            "id": str(row["id"]),
            "kind": row["kind"].value if hasattr(row["kind"], "value") else row["kind"],
            "name": row["name"],
            "source_label": row.get("source_label", ""),
            "target_label": row.get("target_label", ""),
        }

    # -- Edge Annotation ---------------------------------------------------------

    def get_edge_annotation(self, session: Session, tenant_id: UUID, edge_id: str) -> dict[str, Any]:
        """Get annotation attributes on an edge."""
        try:
            e = edges.get(session, tenant_id, UUID(edge_id))
            return {"edge_id": edge_id, "annotation": e.get("annotation") or {}}
        except Exception as exc:
            logger.warning("tool.get_edge_annotation.error", extra={"tenant": str(tenant_id), "edge_id": edge_id}, exc_info=exc)
            raise ServiceError(f"Failed to get annotation for edge {edge_id}: {exc}") from exc

    def set_edge_annotation(
        self, session: Session, tenant_id: UUID, actor: str,
        edge_id: str, version: int, annotation: dict,
    ) -> dict[str, Any]:
        """Set/update annotation on an edge."""
        try:
            eu = EdgeUpdate(version=version, annotation=annotation)
            e = edges.update(session, tenant_id, UUID(edge_id), eu, actor)
            return {"status": "updated", "edge_id": edge_id, "annotation": e.get("annotation") or {}}
        except Exception as exc:
            logger.warning("tool.set_edge_annotation.error", extra={"tenant": str(tenant_id), "edge_id": edge_id}, exc_info=exc)
            raise ServiceError(f"Failed to set annotation for edge {edge_id}: {exc}") from exc

    # -- Graph Rules -------------------------------------------------------------

    def list_graph_rules(
        self,
        session: Session,
        *,
        scope: str | None = None,
        edge_kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List graph rules."""
        try:
            from .enums import RuleScope, EdgeKind
            scope_filter = None
            if scope:
                try:
                    scope_filter = RuleScope(scope)
                except ValueError:
                    pass
            kind_filter = None
            if edge_kind:
                try:
                    kind_filter = EdgeKind(edge_kind)
                except ValueError:
                    pass
            page = graph_rules.list(
                session,
                scopes=[scope_filter] if scope_filter else None,
                edge_kinds=[kind_filter] if kind_filter else None,
                limit=limit, offset=offset,
            )
            items = []
            for r in page.items:
                row = r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r)
                items.append({
                    "id": str(row["id"]),
                    "scope": row["scope"].value if hasattr(row["scope"], "value") else row["scope"],
                    "kind": row["edge_kind"].value if hasattr(row["edge_kind"], "value") else row["edge_kind"],
                    "source_kind": row["source_vertex_kind"].value if hasattr(row["source_vertex_kind"], "value") else row["source_vertex_kind"],
                    "target_kind": row["target_vertex_kind"].value if hasattr(row["target_vertex_kind"], "value") else row["target_vertex_kind"],
                    "source_cardinality": row["source_cardinality"],
                    "target_cardinality": row["target_cardinality"],
                    "duplicate_edges_allowed": row.get("duplicate_edges_allowed", False),
                    "required_attributes": row.get("required_edge_attributes") or [],
                })
            return {"total": page.total, "limit": limit, "offset": offset, "rules": items}
        except Exception as exc:
            logger.warning("tool.list_graph_rules.error", exc_info=exc)
            raise ServiceError(f"Failed to list graph rules: {exc}") from exc

    def get_graph_rule(self, session: Session, rule_id: str) -> dict[str, Any]:
        """Get a single graph rule by ID."""
        try:
            r = graph_rules.get(session, UUID(rule_id))
            row = r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r)
            return {
                "id": str(row["id"]),
                "scope": row["scope"].value if hasattr(row["scope"], "value") else row["scope"],
                "kind": row["edge_kind"].value if hasattr(row["edge_kind"], "value") else row["edge_kind"],
                "source_kind": row["source_vertex_kind"].value if hasattr(row["source_vertex_kind"], "value") else row["source_vertex_kind"],
                "target_kind": row["target_vertex_kind"].value if hasattr(row["target_vertex_kind"], "value") else row["target_vertex_kind"],
                "source_cardinality": row["source_cardinality"],
                "target_cardinality": row["target_cardinality"],
                "duplicate_edges_allowed": row.get("duplicate_edges_allowed", False),
                "required_attributes": row.get("required_edge_attributes") or [],
            }
        except Exception as exc:
            logger.warning("tool.get_graph_rule.error", exc_info=exc)
            raise ServiceError(f"Failed to get graph rule {rule_id}: {exc}") from exc

    def resolve_governing_rule(
        self, session: Session, tenant_id: UUID, edition_id: str,
        edge_kind: str, source_kind: str, target_kind: str,
    ) -> dict[str, Any]:
        """Resolve the governing rule for an edge pattern."""
        try:
            from .enums import EdgeKind, VertexKind, EditionId
            ek = EdgeKind(edge_kind)
            sk = VertexKind(source_kind)
            tk = VertexKind(target_kind)
            eid = EditionId(edition_id)
            rule = validator.resolve_rule(
                session, tenant_id=tenant_id, edition_id=eid,
                edge_kind=ek, source_kind=sk, target_kind=tk,
            )
            if rule is None:
                return {
                    "found": False,
                    "message": f"No rule found for {edge_kind}: {source_kind} -> {target_kind}",
                }
            row = rule
            return {
                "found": True,
                "rule": {
                    "id": str(row["id"]),
                    "scope": row["scope"].value if hasattr(row["scope"], "value") else row["scope"],
                    "kind": row["edge_kind"].value if hasattr(row["edge_kind"], "value") else row["edge_kind"],
                    "source_kind": row["source_vertex_kind"].value if hasattr(row["source_vertex_kind"], "value") else row["source_vertex_kind"],
                    "target_kind": row["target_vertex_kind"].value if hasattr(row["target_vertex_kind"], "value") else row["target_vertex_kind"],
                }
            }
        except Exception as exc:
            logger.warning("tool.resolve_rule.error", exc_info=exc)
            raise ServiceError(f"Failed to resolve rule: {exc}") from exc

    # -- Graph Analysis ----------------------------------------------------------

    def get_neighbors(self, session: Session, tenant_id: UUID, vertex_id: str) -> dict[str, Any]:
        """Find neighbors of a vertex."""
        try:
            src_id = UUID(vertex_id)
            out_edges = edges.list(session, tenant_id, source_vertex_id=src_id, limit=200)
            in_edges = edges.list(session, tenant_id, target_vertex_id=src_id, limit=200)
            outgoing = []
            for e in out_edges.items:
                row = e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
                outgoing.append({
                    "target_id": str(row["target_vertex_id"]),
                    "target_label": row.get("target_label", ""),
                    "kind": row["kind"].value if hasattr(row["kind"], "value") else row["kind"],
                    "name": row["name"],
                })
            incoming = []
            for e in in_edges.items:
                row = e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
                incoming.append({
                    "source_id": str(row["source_vertex_id"]),
                    "source_label": row.get("source_label", ""),
                    "kind": row["kind"].value if hasattr(row["kind"], "value") else row["kind"],
                    "name": row["name"],
                })
            return {
                "vertex_id": vertex_id,
                "outgoing": outgoing,
                "incoming": incoming,
                "outgoing_count": len(outgoing),
                "incoming_count": len(incoming),
            }
        except Exception as exc:
            logger.warning("tool.get_neighbors.error", extra={"tenant": str(tenant_id), "vertex_id": vertex_id}, exc_info=exc)
            raise ServiceError(f"Failed to get neighbors: {exc}") from exc

    def find_paths(self, session: Session, tenant_id: UUID, source_id: str, target_id: str, max_depth: int = 3) -> dict[str, Any]:
        """Find paths between two vertices."""
        try:
            src_id = UUID(source_id)
            tgt_id = UUID(target_id)
            visited = {src_id}
            frontier = [(src_id, [])]
            paths = []
            depth = 0
            while frontier and depth < max_depth:
                next_frontier = []
                for vid, path in frontier:
                    edges_list = edges.list(session, tenant_id, source_vertex_id=vid, limit=200)
                    for e in edges_list.items:
                        row = e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
                        tgt = UUID(row["target_vertex_id"])
                        link = {"to": str(tgt), "via": row["kind"].value if hasattr(row["kind"], "value") else row["kind"]}
                        if tgt == tgt_id:
                            paths.append(path + [link])
                        elif tgt not in visited:
                            visited.add(tgt)
                            next_frontier.append((tgt, path + [link]))
                    in_edges = edges.list(session, tenant_id, target_vertex_id=vid, limit=200)
                    for e in in_edges.items:
                        row = e.model_dump(mode="json") if hasattr(e, "model_dump") else dict(e)
                        src = UUID(row["source_vertex_id"])
                        link = {"from": str(src), "via": row["kind"].value if hasattr(row["kind"], "value") else row["kind"]}
                        if src == tgt_id:
                            paths.append(path + [link])
                        elif src not in visited:
                            visited.add(src)
                            next_frontier.append((src, path + [link]))
                frontier = next_frontier
                depth += 1
            return {"source_id": source_id, "target_id": target_id, "paths": paths, "count": len(paths)}
        except Exception as exc:
            logger.warning("tool.find_paths.error", exc_info=exc)
            raise ServiceError(f"Failed to find paths: {exc}") from exc

    def get_graph_stats(self, session: Session, tenant_id: UUID) -> dict[str, Any]:
        """Get graph statistics."""
        try:
            vertices_page = vertices.list(session, tenant_id, limit=1)
            edges_page = edges.list(session, tenant_id, limit=1)
            rules_page = graph_rules.list(session, limit=1)
            return {
                "vertex_count": vertices_page.total,
                "edge_count": edges_page.total,
                "rule_count": rules_page.total,
            }
        except Exception as exc:
            logger.warning("tool.graph_stats.error", exc_info=exc)
            raise ServiceError(f"Failed to get graph stats: {exc}") from exc

    def check_rule_compliance(
        self, session: Session, tenant_id: UUID, edition_id: str,
        edge_kind: str, source_kind: str, target_kind: str,
        source_lifecycle_state: str | None = None,
        target_lifecycle_state: str | None = None,
        annotation: dict | None = None,
    ) -> dict[str, Any]:
        """Check if a proposed edge complies with governing rules."""
        try:
            from .enums import EdgeKind, VertexKind, EditionId, LifecycleState
            ek = EdgeKind(edge_kind)
            sk = VertexKind(source_kind)
            tk = VertexKind(target_kind)
            eid = EditionId(edition_id)
            resolved, violations = validator.validate_edge(
                session, tenant_id=tenant_id, edition_id=eid,
                edge_kind=ek, source_kind=sk, target_kind=tk,
                source_lifecycle_state=LifecycleState(source_lifecycle_state) if source_lifecycle_state else None,
                target_lifecycle_state=LifecycleState(target_lifecycle_state) if target_lifecycle_state else None,
                annotation=annotation or {},
                tenant_attributes={},
            )
            rule_info = None
            if resolved:
                rule_info = {
                    "id": str(resolved["id"]),
                    "kind": resolved["edge_kind"].value if hasattr(resolved["edge_kind"], "value") else resolved["edge_kind"],
                    "scope": resolved["scope"].value if hasattr(resolved["scope"], "value") else resolved["scope"],
                }
            return {
                "compliant": len(violations) == 0,
                "violations": violations,
                "governing_rule": rule_info,
            }
        except Exception as exc:
            logger.warning("tool.check_rule_compliance.error", exc_info=exc)
            raise ServiceError(f"Failed to check rule compliance: {exc}") from exc

    # -- Dispatch ----------------------------------------------------------------

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        *,
        session: Session,
        tenant_id: UUID,
    ) -> str:
        """Dispatch a tool call requested by the model."""
        args = args or {}
        try:
            if name == "list_documents":
                limit = int(args.get("limit", DEFAULT_LIMIT))
                result = self.list_documents(session, tenant_id, limit=limit)
            elif name == "list_vertices":
                result = self.list_vertices(
                    session, tenant_id,
                    kind=args.get("kind"),
                    lifecycle_state=args.get("lifecycle_state"),
                    limit=int(args.get("limit", 50)),
                    offset=int(args.get("offset", 0)),
                )
            elif name == "get_vertex":
                result = self.get_vertex(session, tenant_id, args["vertex_id"])
            elif name == "create_vertex":
                result = self.create_vertex(
                    session, tenant_id, actor="assistant",
                    kind=args["kind"], number=args["number"], name=args["name"],
                    prefix=args.get("prefix", "V"),
                    revision=args.get("revision", "A"),
                    description=args.get("description", ""),
                    solution_attributes=args.get("solution_attributes"),
                    tenant_attributes=args.get("tenant_attributes"),
                )
            elif name == "update_vertex":
                result = self.update_vertex(
                    session, tenant_id, actor="assistant",
                    vertex_id=args["vertex_id"], version=int(args["version"]),
                    name=args.get("name"), description=args.get("description"),
                    revision=args.get("revision"),
                    lifecycle_state=args.get("lifecycle_state"),
                    release_on=args.get("release_on"),
                    solution_attributes=args.get("solution_attributes"),
                    tenant_attributes=args.get("tenant_attributes"),
                )
            elif name == "delete_vertex":
                result = self.delete_vertex(session, tenant_id, actor="assistant", vertex_id=args["vertex_id"])
            elif name == "list_edges":
                result = self.list_edges(
                    session, tenant_id,
                    kind=args.get("kind"),
                    lifecycle_state=args.get("lifecycle_state"),
                    source_vertex_id=args.get("source_vertex_id"),
                    target_vertex_id=args.get("target_vertex_id"),
                    limit=int(args.get("limit", 50)),
                    offset=int(args.get("offset", 0)),
                )
            elif name == "get_edge":
                result = self.get_edge(session, tenant_id, args["edge_id"])
            elif name == "create_edge":
                result = self.create_edge(
                    session, tenant_id, actor="assistant",
                    kind=args["kind"], name=args["name"],
                    source_vertex_id=args["source_vertex_id"],
                    target_vertex_id=args["target_vertex_id"],
                    annotation=args.get("annotation"),
                    effective_from=args.get("effective_from"),
                    effective_to=args.get("effective_to"),
                )
            elif name == "update_edge":
                result = self.update_edge(
                    session, tenant_id, actor="assistant",
                    edge_id=args["edge_id"], version=int(args["version"]),
                    name=args.get("name"),
                    lifecycle_state=args.get("lifecycle_state"),
                    effective_from=args.get("effective_from"),
                    effective_to=args.get("effective_to"),
                    annotation=args.get("annotation"),
                    tenant_attributes=args.get("tenant_attributes"),
                )
            elif name == "delete_edge":
                result = self.delete_edge(session, tenant_id, actor="assistant", edge_id=args["edge_id"])
            elif name == "get_edge_annotation":
                result = self.get_edge_annotation(session, tenant_id, args["edge_id"])
            elif name == "set_edge_annotation":
                result = self.set_edge_annotation(
                    session, tenant_id, actor="assistant",
                    edge_id=args["edge_id"], version=int(args["version"]),
                    annotation=args["annotation"],
                )
            elif name == "list_graph_rules":
                result = self.list_graph_rules(
                    session,
                    scope=args.get("scope"),
                    edge_kind=args.get("edge_kind"),
                    limit=int(args.get("limit", 50)),
                    offset=int(args.get("offset", 0)),
                )
            elif name == "get_graph_rule":
                result = self.get_graph_rule(session, args["rule_id"])
            elif name == "resolve_governing_rule":
                result = self.resolve_governing_rule(
                    session, tenant_id, edition_id=args.get("edition_id", "foundation"),
                    edge_kind=args["edge_kind"], source_kind=args["source_kind"],
                    target_kind=args["target_kind"],
                )
            elif name == "get_neighbors":
                result = self.get_neighbors(session, tenant_id, args["vertex_id"])
            elif name == "find_paths":
                result = self.find_paths(
                    session, tenant_id,
                    source_id=args["source_id"],
                    target_id=args["target_id"],
                    max_depth=int(args.get("max_depth", 3)),
                )
            elif name == "get_graph_stats":
                result = self.get_graph_stats(session, tenant_id)
            elif name == "check_rule_compliance":
                result = self.check_rule_compliance(
                    session, tenant_id,
                    edition_id=args.get("edition_id", "foundation"),
                    edge_kind=args["edge_kind"],
                    source_kind=args["source_kind"],
                    target_kind=args["target_kind"],
                    source_lifecycle_state=args.get("source_lifecycle_state"),
                    target_lifecycle_state=args.get("target_lifecycle_state"),
                    annotation=args.get("annotation"),
                )
            else:
                return json.dumps({"error": f"unknown tool: {name}"})
            return json.dumps(result)
        except Exception as exc:
            logger.warning("tool.execute.error", extra={"tool": name, "tenant": str(tenant_id)}, exc_info=exc)
            return json.dumps({"error": str(exc)})


#: Pinned singleton used by the assistant.
tools = ToolService()
