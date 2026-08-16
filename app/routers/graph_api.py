"""FastAPI router — read-only graph traversal API (Phase 3).

Exposes JSON traversal over the plmiq node/edge layer populated by
db.indexing.build_graph. Routers mirror existing router patterns
(app/routers/*.py) and run on the tenant-scoped session from get_tenant_db(),
so every traversal is isolated per tenant.

Routes (prefix /graph-api):
    GET  /nodes/{object_id}                → resolve a business object to a node
    GET  /nodes/{object_id}/neighborhood   → direct neighbors
    GET  /nodes/{object_id}/downstream     → downstream traversal
    GET  /nodes/{object_id}/upstream       → upstream traversal
    GET  /nodes/{object_id}/structure      → BOM structure traversal
    GET  /nodes/{object_id}/propagation    → change propagation
    GET  /nodes/{object_id}/path           → path to a target node
    GET  /subgraph                        → edges among a set of node ids
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.database import TenantScopedSession
from app.routers.auth import require_user, get_tenant_db
from app.graph import service

router = APIRouter(prefix="/graph-api", tags=["graph"])


def _resolve_or_404(db, object_id: str) -> dict:
    resolved = service.resolve_node(db, object_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"Node '{object_id}' not found.")
    return resolved


def _node_id_from(object_id: str, db) -> int:
    return _resolve_or_404(db, object_id)["node_id"]


@router.get("/nodes/{object_id}")
def graph_node_detail(object_id: str, request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Resolve a business object to its graph node and return node info."""
    require_user(request, db)
    return _resolve_or_404(db, object_id)


@router.get("/nodes/{object_id}/neighborhood")
def graph_neighborhood(object_id: str, limit: int = Query(100, ge=1, le=500),
                     request: Request = None, db: TenantScopedSession = Depends(get_tenant_db)):
    """Return the direct neighbors (one edge away) of a business object."""
    require_user(request, db)
    nid = _node_id_from(object_id, db)
    return service.neighborhood(db, nid, limit=limit)


@router.get("/nodes/{object_id}/downstream")
def graph_downstream(object_id: str, max_depth: int = Query(5, ge=1, le=15),
                   max_nodes: int = Query(400, ge=1, le=2000),
                   request: Request = None, db: TenantScopedSession = Depends(get_tenant_db)):
    require_user(request, db)
    return service.downstream(db, _node_id_from(object_id, db), max_depth, max_nodes)


@router.get("/nodes/{object_id}/upstream")
def graph_upstream(object_id: str, max_depth: int = Query(5, ge=1, le=15),
                  max_nodes: int = Query(400, ge=1, le=2000),
                  request: Request = None, db: TenantScopedSession = Depends(get_tenant_db)):
    require_user(request, db)
    return service.upstream(db, _node_id_from(object_id, db), max_depth, max_nodes)


@router.get("/nodes/{object_id}/structure")
def graph_structure(object_id: str, max_depth: int = Query(8, ge=1, le=20),
                   max_nodes: int = Query(400, ge=1, le=2000),
                   request: Request = None, db: TenantScopedSession = Depends(get_tenant_db)):
    """Traverse the BOM structure (HAS_COMPONENT) downstream from an assembly."""
    require_user(request, db)
    return service.structure_traversal(db, _node_id_from(object_id, db), max_depth, max_nodes)


@router.get("/nodes/{object_id}/propagation")
def graph_propagation(object_id: str, max_depth: int = Query(8, ge=1, le=20),
                     max_nodes: int = Query(400, ge=1, le=2000),
                     request: Request = None, db: TenantScopedSession = Depends(get_tenant_db)):
    """Change propagation from a change: ECO -> part -> structure -> CAD/doc."""
    require_user(request, db)
    return service.change_propagation(db, _node_id_from(object_id, db), max_depth, max_nodes)


@router.get("/nodes/{object_id}/path")
def graph_path(object_id: str, target: str = Query(...),
              max_depth: int = Query(8, ge=1, le=20),
              request: Request = None, db: TenantScopedSession = Depends(get_tenant_db)):
    """Shortest path from a business object to a target business object."""
    require_user(request, db)
    src = _node_id_from(object_id, db)
    dst = _node_id_from(target, db)
    return {"source": object_id, "target": target, "found": True,
            "path": service.find_path(db, src, dst, max_depth)}


@router.get("/subgraph")
def graph_subgraph(node_ids: str = Query(...),
                 request: Request = None, db: TenantScopedSession = Depends(get_tenant_db)):
    """Return edges whose endpoints are both among the given node ids (comma-separated)."""
    require_user(request, db)
    ids = [n for n in node_ids.split(",") if n.strip().isdigit()]
    return service.subgraph(db, ids)
