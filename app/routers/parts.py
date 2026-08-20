"""Parts CRUD router."""


from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.config import DEFAULT_PAGE_SIZE
from app.database import TenantScopedSession
from app.graph_service import node_edges as domain_node_edges
from app.routers.bom import _build_tree
from app.models import (
    ApprovedManufacturer,
    ApprovedVendor,
    BomItem,
    CadMetadata,
    CostingBomItem,
    EngineeringChangeOrder,
    Favorite,
    Part,
    User,
    WorkflowDefinition,
    WorkflowInstance,
    GraphEdge,
    GraphEdgeType,
    Document,
)
from app.routers.auth import auth_context, get_settings, get_tenant_db, require_role, require_user
from app.sequence import next_object_id
from app.template_utils import render

router = APIRouter(prefix="/parts")


@router.get("", response_class=HTMLResponse)
def list_parts(
    request: Request,
    q: str | None = Query(None, description="Search query"),
    status: str | None = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """List parts with search, filter, and pagination."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    query = db.query(Part)

    if q:
        query = query.filter(
            or_(
                Part.part_number.ilike(f"%{q}%"),
                Part.part_name.ilike(f"%{q}%"),
                Part.material.ilike(f"%{q}%"),
            )
        )
    if status:
        query = query.filter(Part.status == status)

    total = query.count()
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    parts = query.order_by(Part.part_number).offset(offset).limit(DEFAULT_PAGE_SIZE).all()

    return HTMLResponse(content=render(
        "parts/list.html",
        **ctx,
        parts=parts,
        page=page,
        total=total,
        pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        q=q or "",
        status_filter=status or "",
        statuses=get_settings(request).PART_STATUSES,
    ))


@router.get("/new", response_class=HTMLResponse)
def part_new_form(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"]))
):
    """Show part creation form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "parts/new.html", **ctx,
        statuses=get_settings(request).PART_STATUSES,
    ))


@router.get("/{part_number}", response_class=HTMLResponse)
def part_detail(request: Request, part_number: str, db: TenantScopedSession = Depends(get_tenant_db)):
    """Show full part detail with related data."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    part = db.query(Part).filter(Part.part_number == part_number).first()
    if not part:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)

    bom_items = db.query(BomItem).filter(BomItem.part_number == part_number).all()
    costing_items = db.query(CostingBomItem).filter(CostingBomItem.part_number == part_number).all()

    # Expanded BOM subtree rooted at this part (mirrors /bom/tree/{part_number}).
    bom_tree_items = []
    _bom_seen = set()
    _bom_visited = set()
    frontier = [part_number]
    while frontier:
        current = frontier.pop()
        if current in _bom_visited:
            continue
        _bom_visited.add(current)
        rows = (
            db.query(BomItem).options(selectinload(BomItem.part))
            .filter((BomItem.part_number == current) | (BomItem.parent_assembly == current))
            .order_by(BomItem.level, BomItem.part_number)
            .all()
        )
        for row in rows:
            if row.id not in _bom_seen:
                _bom_seen.add(row.id)
                bom_tree_items.append(row)
                if row.part_number != current:
                    frontier.append(row.part_number)
    bom_tree = _build_tree(bom_tree_items)

    bom_costing_items = []
    total_bom_cost = 0.0
    if bom_tree_items:
        part_numbers_in_bom = {b.part_number for b in bom_tree_items if b.part_number != part_number}
        part_revisions = {
            p.part_number: p.part_revision
            for p in db.query(Part.part_number, Part.part_revision)
            .filter(Part.part_number.in_(part_numbers_in_bom))
            .all()
        }
        costing_map = {
            c.part_number: c
            for c in db.query(CostingBomItem)
            .filter(CostingBomItem.part_number.in_(part_numbers_in_bom))
            .all()
        }
        for bom_item in bom_tree_items:
            if bom_item.part_number == part_number:
                continue
            cost = costing_map.get(bom_item.part_number)
            unit_cost = float(cost.unit_cost) if cost and cost.unit_cost else 0.0
            extended = float(bom_item.qty or 0) * unit_cost
            total_bom_cost += extended
            bom_costing_items.append({
                "part_number": bom_item.part_number,
                "part_revision": part_revisions.get(bom_item.part_number, "-"),
                "part_name": bom_item.part_name,
                "qty": bom_item.qty,
                "uom": bom_item.uom,
                "unit_cost": unit_cost,
                "extended_cost": extended,
                "level": bom_item.level,
            })
    ecos = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.part_number == part_number).all()
    amls = db.query(ApprovedManufacturer).filter(ApprovedManufacturer.part_number == part_number).all()
    avls = db.query(ApprovedVendor).filter(ApprovedVendor.part_number == part_number).all()
    cads = db.query(CadMetadata).filter(CadMetadata.part_number == part_number).all()
    graph_edges = domain_node_edges(db, "PART", part_number)

    part_docs = []
    if part.node_id:
        edges = db.query(GraphEdge).filter(
            (GraphEdge.source_node_id == part.node_id) | (GraphEdge.target_node_id == part.node_id)
        ).all()
        doc_edge_types = {
            "HAS_SPEC", "HAS_MANUAL", "HAS_CERTIFICATE", "HAS_DRAWING",
            "HAS_REPORT", "HAS_CONTRACT", "HAS_STANDARD", "HAS_OTHER", "HAS_DOCUMENT",
        }
        if edges:
            edge_type_ids = {e.edge_type_id for e in edges if e.target_node_id and e.source_node_id}
            edge_types = {et.id: et.name for et in db.query(GraphEdgeType).filter(GraphEdgeType.id.in_(edge_type_ids)).all()}
            doc_node_ids = {e.target_node_id for e in edges if edge_types.get(e.edge_type_id) in doc_edge_types}
            if doc_node_ids:
                docs = db.query(Document).filter(Document.node_id.in_(doc_node_ids)).all()
                doc_map = {d.node_id: d for d in docs}
                for e in edges:
                    etype = edge_types.get(e.edge_type_id)
                    if etype not in doc_edge_types:
                        continue
                    doc = doc_map.get(e.target_node_id if e.source_node_id == part.node_id else e.source_node_id)
                    if doc:
                        part_docs.append({
                            "id": doc.id,
                            "name": doc.name,
                            "document_number": doc.document_number,
                            "doc_format": doc.doc_format,
                            "status": doc.status,
                            "edge_type": etype,
                        })
    part_docs.sort(key=lambda x: (x["edge_type"], x["name"]))

    # Query global templates + this tenant's templates (bypass tenant_key scoping)
    release_templates = (
        db.execute(select(WorkflowDefinition).where(
            WorkflowDefinition.object_type == "part",
            (WorkflowDefinition.is_global == True) |
            (WorkflowDefinition.tenant_id == user.tenant_id),
            WorkflowDefinition.is_active == True,  # noqa: E712
        ).order_by(WorkflowDefinition.name)).scalars().all()
    )
    # Query global + tenant-specific Unrelease templates (applies to any object type)
    unrelease_templates = (
        db.execute(select(WorkflowDefinition).where(
            (WorkflowDefinition.is_global == True) |
            (WorkflowDefinition.tenant_id == user.tenant_id),
            WorkflowDefinition.is_active == True,  # noqa: E712
            WorkflowDefinition.name == "Unrelease",
        )).scalars().all()
    )
    # in_workflow flag is set on the part by the workflow engine
    release_instance = (
        db.query(WorkflowInstance).filter(
            WorkflowInstance.object_type == "part",
            WorkflowInstance.object_id == part_number,
            WorkflowInstance.tenant_id == user.tenant_id,
        ).order_by(WorkflowInstance.id.desc()).first()
    )

    return HTMLResponse(content=render(
        "parts/detail.html",
        **ctx,
        part=part,
        bom_items=bom_items,
        costing_items=costing_items,
        bom_costing_items=bom_costing_items,
        total_bom_cost=total_bom_cost,
        ecos=ecos,
        amls=amls,
        avls=avls,
        cads=cads,
        graph_edges=graph_edges,
        bom_tree=bom_tree,
        release_templates=release_templates,
        unrelease_templates=unrelease_templates,
        release_instance=release_instance,
        part_docs=part_docs,
    ))


@router.get("/{part_number}/edit", response_class=HTMLResponse)
def part_edit_form(
    request: Request,
    part_number: str,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"]))
):
    """Show part edit form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    part = db.query(Part).filter(Part.part_number == part_number).first()
    if not part:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    # Check if this part is in user's favorites
    is_favorite = db.query(Favorite).filter(
        Favorite.user_id == user.user_id,
        Favorite.object_type == "part",
        Favorite.object_id == part_number,
    ).first() is not None

    return HTMLResponse(content=render(
        "parts/edit.html", **ctx,
        part=part,
        statuses=get_settings(request).PART_STATUSES,
        is_favorite=is_favorite,
    ))


@router.post("/{part_number}/edit", response_class=HTMLResponse)
def part_edit_submit(
    request: Request,
    part_number: str,
    part_name: str = Form(...),
    part_revision: str = Form(...),
    material: str = Form(""),
    uom: str = Form("EA"),
    qty: int = Form(1),
    status: str = Form("DRAFT"),
    spec_file: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"]))
):
    """Update part and redirect."""
    user = require_user(request, db)
    part = db.query(Part).filter(Part.part_number == part_number).first()
    if not part:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    part.part_name = part_name
    part.part_revision = part_revision
    part.material = material or None
    part.uom = uom or "EA"
    part.qty = qty
    part.status = status or "DRAFT"
    part.spec_file = spec_file or None
    db.commit()
    return RedirectResponse(url=f"/parts/{part_number}", status_code=303)


@router.post("/new", response_class=HTMLResponse)
def part_new_submit(
    request: Request,
    part_number: str = Form(...),
    part_name: str = Form(...),
    part_revision: str = Form("A"),
    material: str = Form(""),
    uom: str = Form("EA"),
    qty: int = Form(1),
    status: str = Form("DRAFT"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"]))
):
    """Create new part."""
    user = require_user(request, db)
    tenant_key = user.tenant_key if user else None
    part_number = part_number or next_object_id(db, "part", tenant_key)
    part = Part(
        part_number=part_number,
        part_name=part_name,
        part_revision=part_revision or "A",
        material=material or None,
        uom=uom or "EA",
        qty=qty,
        status=status or "DRAFT",
        tenant_id=1,
    )
    db.add(part)
    db.commit()
    return RedirectResponse(url=f"/parts/{part_number}", status_code=303)


@router.post("/{part_number}/delete", response_class=HTMLResponse)
def part_delete(
    request: Request,
    part_number: str,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"]))
):
    """Delete a part and redirect to the list."""
    user = require_user(request, db)
    part = db.query(Part).filter(Part.part_number == part_number).first()
    if part:
        db.delete(part)
        db.commit()
    return RedirectResponse(url="/parts", status_code=303)
