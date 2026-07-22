"""ECO router."""

from typing import Optional, Dict
from fastapi import APIRouter, Depends, Query, Form, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_db
from app.models import EngineeringChangeOrder, User, WorkflowTemplate, WorkflowInstance, Favorite
from app.config import DEFAULT_PAGE_SIZE
from app.routers.auth import require_user, require_role, auth_context
from app.template_utils import render
from app.workflow.engine import active_instance

router = APIRouter(prefix="/eco")


@router.get("", response_class=HTMLResponse)
def list_ecos(
    request: Request,
    q: Optional[str] = Query(None, description="Search"),
    status: Optional[str] = Query(None, description="Filter by ECO status"),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
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
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show ECO creation form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "eco/new.html", **ctx,
        statuses=["DRAFT", "REVIEW", "APPROVED"],
    ))


@router.get("/{eco_number}", response_class=HTMLResponse)
def eco_detail(request: Request, eco_number: str, db: Session = Depends(get_db)):
    """Show ECO detail."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == eco_number).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)

    release_templates = (
        db.query(WorkflowTemplate).filter(
            WorkflowTemplate.object_type == "eco",
            WorkflowTemplate.tenant_id == user.tenant_id,
            WorkflowTemplate.is_active == True,  # noqa: E712
        ).order_by(WorkflowTemplate.name).all()
    )
    active_release = active_instance(db, "eco", eco_number)
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
        active_release=active_release,
        release_instance=release_instance,
    ))


@router.get("/{eco_number}/edit", response_class=HTMLResponse)
def eco_edit_form(
    request: Request,
    eco_number: str,
    db: Session = Depends(get_db),
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

    return HTMLResponse(content=render("eco/edit.html", **ctx, item=item, statuses=["DRAFT", "REVIEW", "APPROVED"], is_favorite=is_favorite))


@router.post("/{eco_number}/edit", response_class=HTMLResponse)
def eco_edit_submit(
    request: Request,
    eco_number: str,
    eco_title: str = Form(...),
    eco_description: str = Form(""),
    eco_status: str = Form("DRAFT"),
    change_type: str = Form(""),
    change_detail: str = Form(""),
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    """Update ECO and redirect."""
    user = require_user(request, db)
    item = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == eco_number).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    item.eco_title = eco_title
    item.eco_description = eco_description or None
    item.eco_status = eco_status or "DRAFT"
    item.change_type = change_type or None
    item.change_detail = change_detail or None
    db.commit()
    return RedirectResponse(url=f"/eco/{eco_number}", status_code=303)


@router.post("/new", response_class=HTMLResponse)
def eco_new_submit(
    request: Request,
    eco_number: str = Form(...),
    eco_title: str = Form(...),
    part_number: str = Form(...),
    eco_description: str = Form(""),
    eco_status: str = Form("DRAFT"),
    change_type: str = Form(""),
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    """Create new ECO."""
    user = require_user(request, db)
    item = EngineeringChangeOrder(
        eco_number=eco_number,
        eco_title=eco_title,
        part_number=part_number,
        eco_description=eco_description or None,
        eco_status=eco_status or "DRAFT",
        change_type=change_type or None,
        tenant_id=1,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/eco/{eco_number}", status_code=303)


@router.post("/{eco_number}/delete", response_class=HTMLResponse)
def eco_delete(
    request: Request,
    eco_number: str,
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    """Delete an ECO and redirect to the list."""
    user = require_user(request, db)
    item = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == eco_number).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/eco", status_code=303)