"""ECO router."""

from typing import Optional, Dict
from fastapi import APIRouter, Depends, Query, Form, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import TenantScopedSession
from app.models import EngineeringChangeOrder, User, WorkflowDefinition, WorkflowInstance, Favorite
from app.config import DEFAULT_PAGE_SIZE
from app.routers.auth import require_user, require_role, auth_context, get_tenant_db
from app.template_utils import render

router = APIRouter(prefix="/eco")


@router.get("", response_class=HTMLResponse)
def list_ecos(
    request: Request,
    q: Optional[str] = Query(None, description="Search"),
    status: Optional[str] = Query(None, description="Filter by ECO status"),
    page: int = Query(1, ge=1),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """List engineering change orders."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    query = db.query(EngineeringChangeOrder)

    if q:
        query = query.filter(
            or_(
                EngineeringChangeOrder.eco_number.ilike(f"%{q}%"),
                EngineeringChangeOrder.eco_title.ilike(f"%{q}%"),
                EngineeringChangeOrder.part_number.ilike(f"%{q}%"),
            )
        )
    if status:
        query = query.filter(EngineeringChangeOrder.eco_status == status)

    total = query.count()
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    items = query.order_by(EngineeringChangeOrder.drafted_date.desc().nullsfirst()).offset(offset).limit(DEFAULT_PAGE_SIZE).all()

    return HTMLResponse(content=render(
        "eco/list.html",
        **ctx,
        items=items,
        page=page,
        total=total,
        pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        q=q or "",
        status_filter=status or "",
        statuses=["DRAFT", "REVIEW", "APPROVED"],
    ))


@router.get("/new", response_class=HTMLResponse)
def eco_new_form(
    request: Request,
    q: Optional[str] = Query(None),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show ECO creation form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    change_types = ["DESIGN_CHANGE", "MFG_CHANGE", "ASSEMBLY_CHANGE"]
    return HTMLResponse(content=render(
        "eco/new.html", **ctx,
        statuses=["DRAFT", "REVIEW", "APPROVED"],
        change_types=change_types,
        form_change_type=q or "",
    ))


@router.get("/{eco_number}", response_class=HTMLResponse)
def eco_detail(request: Request, eco_number: str, db: TenantScopedSession = Depends(get_tenant_db)):
    """Show ECO detail."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == eco_number).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)

    # Query global templates + this tenant's templates (bypass tenant_key scoping)
    release_templates = db.execute(select(WorkflowDefinition).where(
        WorkflowDefinition.object_type == "eco",
        (WorkflowDefinition.is_global == True) |
        (WorkflowDefinition.tenant_id == user.tenant_id),
        WorkflowDefinition.is_active == True,  # noqa: E712
    ).order_by(WorkflowDefinition.name)).scalars().all()
    # Query global + tenant-specific Unrelease templates (applies to any object type)
    unrelease_templates = db.execute(select(WorkflowDefinition).where(
        (WorkflowDefinition.is_global == True) |
        (WorkflowDefinition.tenant_id == user.tenant_id),
        WorkflowDefinition.is_active == True,  # noqa: E712
        WorkflowDefinition.name == "Unrelease",
    )).scalars().all()
    # in_workflow flag is set on the ECO by the workflow engine
    release_instance = (
        db.query(WorkflowInstance).filter(
            WorkflowInstance.object_type == "eco",
            WorkflowInstance.object_id == eco_number,
            WorkflowInstance.tenant_id == user.tenant_id,
        ).order_by(WorkflowInstance.id.desc()).first()
    )

    return HTMLResponse(content=render(
        "eco/detail.html", **ctx, item=item,
        release_templates=release_templates,
        unrelease_templates=unrelease_templates,
        release_instance=release_instance,
    ))


@router.get("/{eco_number}/edit", response_class=HTMLResponse)
def eco_edit_form(
    request: Request,
    eco_number: str,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show ECO edit form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == eco_number).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)

    # Check if this ECO is in user's favorites
    is_favorite = db.query(Favorite).filter(
        Favorite.user_id == user.user_id,
        Favorite.object_type == "eco",
        Favorite.object_id == eco_number,
    ).first() is not None

    # Build user dropdown for change_drafter/change_approver
    users_for_select = db.query(User).filter(
        User.tenant_id == user.tenant_id,
        User.is_active == True,  # noqa: E712
    ).order_by(User.username).all()

    change_types = ["DESIGN_CHANGE", "MFG_CHANGE", "ASSEMBLY_CHANGE"]

    return HTMLResponse(content=render("eco/edit.html", **ctx, item=item, statuses=["DRAFT", "REVIEW", "APPROVED"], is_favorite=is_favorite, users=users_for_select, change_types=change_types))


@router.post("/{eco_number}/edit", response_class=HTMLResponse)
def eco_edit_submit(
    request: Request,
    eco_number: str,
    eco_title: str = Form(...),
    part_number: str = Form(""),
    eco_description: str = Form(""),
    eco_status: str = Form("DRAFT"),
    current_revision: str = Form("A"),
    new_revision: str = Form("B"),
    change_type: str = Form(""),
    change_detail: str = Form(""),
    affected_bom_level: int = Form(0),
    change_drafter: Optional[str] = Form(""),
    change_approver: Optional[str] = Form(""),
    drafted_date: str = Form(""),
    approved_date: str = Form(""),
    implemented_date: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Update ECO and redirect."""
    user = require_user(request, db)
    item = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == eco_number).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    item.eco_title = eco_title
    item.part_number = part_number or None
    item.eco_description = eco_description or None
    item.eco_status = eco_status or "DRAFT"
    item.current_revision = current_revision or None
    item.new_revision = new_revision or None
    item.change_type = change_type or None
    item.change_detail = change_detail or None
    item.affected_bom_level = affected_bom_level or None
    item.change_drafter = int(change_drafter) if change_drafter else None
    item.change_approver = int(change_approver) if change_approver else None
    item.drafted_date = drafted_date or None
    item.approved_date = approved_date or None
    item.implemented_date = implemented_date or None
    item.modified_by = user.user_id
    db.commit()
    return RedirectResponse(url=f"/eco/{eco_number}", status_code=303)


@router.post("/new", response_class=HTMLResponse)
def eco_new_submit(
    request: Request,
    eco_number: str = Form(...),
    eco_title: str = Form(...),
    part_number: str = Form(""),
    eco_description: str = Form(""),
    eco_status: str = Form("DRAFT"),
    current_revision: str = Form("A"),
    new_revision: str = Form("B"),
    change_type: str = Form(""),
    change_detail: str = Form(""),
    affected_bom_level: int = Form(0),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Create new ECO."""
    user = require_user(request, db)
    item = EngineeringChangeOrder(
        eco_number=eco_number,
        eco_title=eco_title,
        part_number=part_number or None,
        eco_description=eco_description or None,
        eco_status=eco_status or "DRAFT",
        current_revision=current_revision or "A",
        new_revision=new_revision or "B",
        change_type=change_type or None,
        change_detail=change_detail or None,
        affected_bom_level=affected_bom_level or None,
        created_by=user.user_id,
        modified_by=user.user_id,
        tenant_id=user.tenant_id,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/eco/{eco_number}", status_code=303)


@router.post("/{eco_number}/delete", response_class=HTMLResponse)
def eco_delete(
    request: Request,
    eco_number: str,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Delete an ECO and redirect to the list."""
    user = require_user(request, db)
    item = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == eco_number).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/eco", status_code=303)