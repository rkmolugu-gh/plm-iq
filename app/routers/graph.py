"""Graph traversal router — render connectivity view for a business object."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.database import TenantScopedSession
from app.graph_service import build_tree, tree_to_lines, resolve_root
from app.routers.auth import require_user, auth_context, get_tenant_db
from app.template_utils import render

router = APIRouter(prefix="/graph")


@router.get("/{object_id}", response_class=HTMLResponse)
def graph_detail(object_id: str, request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Show the connectivity graph for a business object.

    The page shell is lightweight: existence and the breadcrumb back-link are
    derived from the domain object (resolve_root). All traversal data is fetched
    client-side from the /graph-api endpoints (app.routers.graph_api), so the
    page exercises neighborhood, upstream, downstream, structure, propagation,
    path and subgraph through the new plmiq layer.
    """
    user = require_user(request, db)
    ctx = auth_context(request, db)

    # Find the object's canonical page for the breadcrumb back-link.
    info = resolve_root(db, object_id)
    if info is None:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    object_type = info[0]
    back_url = {
        "PART": f"/parts/{object_id}",
        "ECO": f"/eco/{object_id}",
        "SUPPLIER": None,
        "CAD_MODEL": None,
        "DOCUMENT": None,
    }.get(object_type, None)

    return HTMLResponse(content=render(
        "graph/detail.html",
        **ctx,
        object_id=object_id,
        object_type=object_type,
        back_url=back_url,
    ))


@router.get("/{object_id}/export", response_class=PlainTextResponse)
def graph_export(object_id: str, request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Download the hierarchical traversal as a text file."""
    require_user(request, db)
    root = build_tree(db, object_id)
    if root is None:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    body = "\n".join(tree_to_lines(root))
    filename = f"graph-{object_id}.txt"
    # RFC 5987 filename* for non-ASCII ids; fall back to ascii-safe name.
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in filename)
    disposition = f'attachment; filename="{safe}"; filename*=UTF-8\'\'{safe}'
    return PlainTextResponse(body, media_type="text/plain",
                             headers={"Content-Disposition": disposition})
