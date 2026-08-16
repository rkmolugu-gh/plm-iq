"""Graph traversal service over the plmiq_graph layer (Phase 3).

Read-only traversal over the normalized node/edge tables populated by
db.indexing.build_graph (Phase 2). Edges are stored once in their canonical
direction; the inverse traversal label comes from plmiq_edge_type.inverse_type.

Every function operates on a tenant-scoped session
(app.database.TenantScopedSession) so node/edge lookups stay isolated per
tenant. Edge-type names are resolved through the ORM relationship (which loads
globally), since the edge-type catalog is a governed, non-tenant-specific
vocabulary.

See docs/plm-iq-graph-concepts.txt for the vocabulary and phase plan.
"""

from __future__ import annotations

from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import (
    Part,
    CostingBomItem,
    EngineeringChangeOrder,
    ApprovedManufacturer,
    ApprovedVendor,
    CadMetadata,
    Document,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowTask,
    User,
    Tenant,
    GraphNode,
    GraphEdge,
    GraphEdgeType,
)

# --- Edge-type names used for structure / trace traversals ----------------------
STRUCTURE_EDGE_TYPES = {"HAS_COMPONENT"}
TRACE_EDGE_TYPES = {"AFFECTS", "CHANGES", "HAS_COMPONENT", "HAS_CAD", "HAS_DOCUMENT"}

# Ordered node-type resolvers: (model, object_type, key, label) callables.
NODE_LOOKUPS = [
    (Tenant, "ORGANIZATION", lambda r: r.tenant_id, lambda r: r.tenant_name),
    (User, "USER", lambda r: r.user_id, lambda r: r.username or r.full_name),
    (Part, "PART", lambda r: r.part_number, lambda r: r.part_name),
    (CostingBomItem, "COST", lambda r: r.id, lambda r: f"Cost {r.part_number} L{r.level}"),
    (EngineeringChangeOrder, "ENGINEERING_CHANGE", lambda r: r.eco_number, lambda r: r.eco_title),
    (ApprovedManufacturer, "SUPPLIER", lambda r: r.id, lambda r: f"MFR:{r.manufacturer_name}"),
    (ApprovedVendor, "SUPPLIER", lambda r: r.id, lambda r: f"VND:{r.vendor_name}"),
    (CadMetadata, "CAD_MODEL", lambda r: r.id, lambda r: r.cad_file_name),
    (Document, "DOCUMENT", lambda r: r.id, lambda r: r.title or r.name),
    (WorkflowDefinition, "WORKFLOW", lambda r: r.id, lambda r: r.name),
    (WorkflowInstance, "WORKFLOW_INSTANCE", lambda r: r.id, lambda r: r.object_id),
    (WorkflowTask, "WORKFLOW_TASK", lambda r: r.id, lambda r: r.step_name or f"Task {r.id}"),
]


def node_info(db: Session, node_id: int) -> Optional[dict]:
    """Resolve a plmiq_node_id to its business-object type, key and label.

    The registry stores no type on the node; the owning domain row supplies it,
    so we scan the node-capable models for the row carrying this node_id.
    """
    for model, otype, key_fn, label_fn in NODE_LOOKUPS:
        row = db.query(model).filter(model.node_id == node_id).first()
        if row is not None:
            label = label_fn(row) or key_fn(row)
            return {
                "node_id": node_id,
                "object_type": otype,
                "object_key": key_fn(row),
                "label": label,
                "node_label": label,
            }
    fallback = db.query(GraphNode).filter(GraphNode.node_id == node_id).first()
    return {
        "node_id": node_id,
        "object_type": "NODE",
        "object_key": str(node_id),
        "label": fallback.node_label if fallback and fallback.node_label else f"node-{node_id}",
        "node_label": fallback.node_label if fallback and fallback.node_label else f"node-{node_id}",
    }


def resolve_node(db: Session, object_id: str) -> Optional[dict]:
    """Map a business-object identifier to its graph node + resolved info.

    Supports the primary hub types: PART, ENGINEERING_CHANGE, DOCUMENT,
    CAD_MODEL, SUPPLIER (AML/AVL by name). Returns None when no node exists.
    """
    part = db.query(Part).filter(Part.part_number == object_id).first()
    if part and part.node_id:
        return {"node_id": part.node_id, "object_type": "PART",
                "object_key": part.part_number, "label": part.part_name or part.part_number,
                "path": f"/parts/{part.part_number}"}
    eco = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == object_id).first()
    if eco and eco.node_id:
        return {"node_id": eco.node_id, "object_type": "ENGINEERING_CHANGE",
                "object_key": eco.eco_number, "label": eco.eco_title or eco.eco_number,
                "path": f"/eco/{eco.eco_number}"}
    doc = db.query(Document).filter(Document.name == object_id).first()
    if doc and doc.node_id:
        return {"node_id": doc.node_id, "object_type": "DOCUMENT",
                "object_key": doc.id, "label": doc.title or doc.name, "path": None}
    cad = db.query(CadMetadata).filter(CadMetadata.cad_file_name == object_id).first()
    if cad and cad.node_id:
        return {"node_id": cad.node_id, "object_type": "CAD_MODEL",
                "object_key": cad.id, "label": cad.cad_file_name, "path": None}
    aml = db.query(ApprovedManufacturer).filter(ApprovedManufacturer.manufacturer_name == object_id).first()
    if aml and aml.node_id:
        return {"node_id": aml.node_id, "object_type": "SUPPLIER",
                "object_key": aml.id, "label": f"MFR:{aml.manufacturer_name}", "path": None}
    avl = db.query(ApprovedVendor).filter(ApprovedVendor.vendor_name == object_id).first()
    if avl and avl.node_id:
        return {"node_id": avl.node_id, "object_type": "SUPPLIER",
                "object_key": avl.id, "label": f"VND:{avl.vendor_name}", "path": None}
    return None


# --- Low-level helpers ------------------------------------------------------

def _edge_type_name(edge) -> str:
    return edge.edge_type.name if edge.edge_type else str(edge.edge_type_id)


def _reverse_type(edge) -> str:
    return edge.edge_type.inverse_type if edge.edge_type else str(edge.edge_type_id)


def _node_label(edge, use_source: bool) -> str:
    node = edge.source_node if use_source else edge.target_node
    return node.node_label if node and node.node_label else ""


def neighborhood(db: Session, node_id: int, limit: int = 100) -> dict:
    """Direct neighbors (nodes one edge away) of a node.

    Returns {node: <info>, edges: [ {edge_type, direction, node_id, label} ]}.
    'direction' is relative to the queried node ('out' = downstream, 'in' =
    upstream). Incoming edges are labeled with the inverse edge type.
    """
    info = node_info(db, node_id)
    if info is None:
        return None
    edges = []
    seen = set()
    for edge in _outgoing(db, node_id):
        if len(edges) >= limit:
            break
        seen.add(edge.target_node_id)
        edges.append({
            "edge_type": _edge_type_name(edge),
            "direction": "out",
            "node_id": edge.target_node_id,
            "label": _node_label(edge, use_source=False),
        })
    for edge in _incoming(db, node_id):
        if len(edges) >= limit:
            break
        if edge.source_node_id in seen:
            continue
        edges.append({
            "edge_type": _reverse_type(edge),
            "direction": "in",
            "node_id": edge.source_node_id,
            "label": _node_label(edge, use_source=True),
        })
    return {"node": info, "edge_count": len(edges), "edges": edges}


# --- Directional BFS traversals ----------------------------------------------

def _walk(db, start: int, direction: str, max_depth: int, max_nodes: int,
          edge_types: Optional[Iterable[str]] = None) -> list[dict]:
    """BFS over outgoing ('down') or incoming ('up') edges."""
    allowed = set(edge_types) if edge_types is not None else None
    visited: set[int] = {start}
    frontier = [start]
    depth = 0
    result: list[dict] = []
    while frontier and depth < max_depth and len(visited) <= max_nodes:
        depth += 1
        nxt = []
        for current in frontier:
            edges = _outgoing(db, current) if direction == "down" else _incoming(db, current)
            for edge in edges:
                etype = _edge_type_name(edge)
                if allowed is not None and etype not in allowed:
                    continue
                neighbor = edge.target_node_id if direction == "down" else edge.source_node_id
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                if len(visited) > max_nodes:
                    break
                edge_label = _edge_type_name(edge) if direction == "down" else _reverse_type(edge)
                ninfo = node_info(db, neighbor)
                ninfo["edge_type"] = edge_label
                ninfo["from_node_id"] = current
                ninfo["depth"] = depth
                result.append(ninfo)
                nxt.append(neighbor)
        frontier = nxt
    return result


def downstream(db, node_id: int, max_depth: int = 5, max_nodes: int = 400,
              edge_types: Optional[Iterable[str]] = None) -> list[dict]:
    return _walk(db, node_id, "down", max_depth, max_nodes, edge_types)


def upstream(db, node_id: int, max_depth: int = 5, max_nodes: int = 400,
            edge_types: Optional[Iterable[str]] = None) -> list[dict]:
    return _walk(db, node_id, "up", max_depth, max_nodes, edge_types)


def structure_traversal(db, node_id: int, max_depth: int = 8, max_nodes: int = 400) -> list[dict]:
    """Traverse the BOM structure (follow HAS_COMPONENT) downstream."""
    return _walk(db, node_id, "down", max_depth, max_nodes, STRUCTURE_EDGE_TYPES)


def change_propagation(db, node_id: int, max_depth: int = 8, max_nodes: int = 400) -> list[dict]:
    """Change propagation: ECO -> affected part -> structure -> CAD/doc."""
    return _walk(db, node_id, "down", max_depth, max_nodes, TRACE_EDGE_TYPES)


# --- Path finding -----------------------------------------------------------

def find_path(db: Session, source: int, target: int, max_depth: int = 8) -> Optional[list[dict]]:
    """Shortest path (by BFS) from source to target, or None."""
    if source == target:
        return []
    parent: dict[int, tuple[int, int]] = {}  # node -> (previous_node, edge_id)
    visited: set[int] = {source}
    frontier = [source]
    depth = 0
    found = False
    while frontier and depth < max_depth:
        depth += 1
        nxt = []
        for current in frontier:
            for edge in _outgoing(db, current):
                if edge.target_node_id in visited:
                    continue
                visited.add(edge.target_node_id)
                parent[edge.target_node_id] = (current, edge.id)
                if edge.target_node_id == target:
                    found = True
                    break
                nxt.append(edge.target_node_id)
            if found:
                break
        if found:
            break
        frontier = nxt
    if not found:
        return None
    # Reconstruct path
    path_edges = []
    cur = target
    while cur != source:
        prev, edge_id = parent[cur]
        edge = db.query(GraphEdge).filter(GraphEdge.id == edge_id).first()
        path_edges.append({
            "from": prev,
            "to": cur,
            "edge_type": _edge_type_name(edge),
        })
        cur = prev
    path_edges.reverse()
    return path_edges


def subgraph(db: Session, node_ids: Iterable[int]) -> dict:
    """Return edges whose endpoints both lie in node_ids, plus node info."""
    idset = set(int(n) for n in node_ids)
    edges = db.query(GraphEdge).filter(
        GraphEdge.source_node_id.in_(idset),
        GraphEdge.target_node_id.in_(idset),
    ).all()
    return {
        "node_ids": sorted(idset),
        "edge_count": len(edges),
        "edges": [
            {
                "edge_type": _edge_type_name(e),
                "source_node_id": e.source_node_id,
                "source_label": _node_label(e, use_source=True),
                "target_node_id": e.target_node_id,
                "target_label": _node_label(e, use_source=False),
            }
            for e in edges
        ],
    }
