"""Parts CRUD router."""

from typing import Optional
from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import TenantScopedSession
from app.models import Part, BomItem, CostingBomItem, EngineeringChangeOrder, ApprovedManufacturer, ApprovedVendor, CadMetadata, User, WorkflowDefinition, WorkflowInstance, Favorite
from app.config import DEFAULT_PAGE_SIZE
from app.routers.auth import require_user, require_role, auth_context, get_tenant_db
from app.template_utils import render

router = APIRouter(prefix="/parts")


@router.get("", response_class=HTMLResponse)
def list_parts(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    status: Optional[str] = Query(None, description="Filter by status"),
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
        statuses=["DRAFT", "RELEASED", "OBSOLETED"],
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
        statuses=["DRAFT", "RELEASED", "OBSOLETED"],
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
    ecos = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.part_number == part_number).all()
    amls = db.query(ApprovedManufacturer).filter(ApprovedManufacturer.part_number == part_number).all()
    avls = db.query(ApprovedVendor).filter(ApprovedVendor.part_number == part_number).all()
    cads = db.query(CadMetadata).filter(CadMetadata.part_number == part_number).all()

    # Query global templates + this tenant's templates (bypass tenant_key scoping)
    release_templates = (
        db.execute(select(WorkflowDefinition).where(
            WorkflowDefinition.object_type == "part",
            (WorkflowDefinition.is_global == True) |
            (WorkflowDefinition.tenant_id == user.tenant_id),
            WorkflowDefinition.is_active == True,  # noqa: E712
        ).order_by(WorkflowDefinition.name)).scalars().all()
    )
    unrelease_templates = (
        db.execute(select(WorkflowDefinition).where(
            WorkflowDefinition.object_type == "part",
            (WorkflowDefinition.is_global == True) |
            (WorkflowDefinition.tenant_id == user.tenant_id),
            WorkflowDefinition.is_active == True,  # noqa: E712
            WorkflowDefinition.name == "Unrelease",
        ).order_by(WorkflowDefinition.name)).scalars().all()
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
        ecos=ecos,
        amls=amls,
        avls=avls,
        cads=cads,
        release_templates=release_templates,
        unrelease_templates=unrelease_templates,
        release_instance=release_instance,
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
        statuses=["DRAFT", "RELEASED", "OBSOLETED"],
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
