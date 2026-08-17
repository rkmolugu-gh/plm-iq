"""AML router."""

from typing import Optional, Dict
from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import TenantScopedSession
from app.models import ApprovedManufacturer, User
from app.config import DEFAULT_PAGE_SIZE
from app.routers.auth import require_user, require_role, auth_context, get_tenant_db
from app.sequence import next_object_id
from app.template_utils import render

router = APIRouter(prefix="/aml")


@router.get("", response_class=HTMLResponse)
def list_aml(
    request: Request,
    q: Optional[str] = Query(None, description="Search"),
    preferred: Optional[str] = Query(None, description="Preferred only"),
    page: int = Query(1, ge=1),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """List approved manufacturers."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    query = db.query(ApprovedManufacturer)

    if q:
        query = query.filter(
            or_(
                ApprovedManufacturer.part_number.ilike(f"%{q}%"),
                ApprovedManufacturer.manufacturer_name.ilike(f"%{q}%"),
            )
        )
    if preferred == "Yes":
        query = query.filter(ApprovedManufacturer.preferred_flag == "Yes")

    total = query.count()
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    items = query.order_by(ApprovedManufacturer.part_number).offset(offset).limit(DEFAULT_PAGE_SIZE).all()

    return HTMLResponse(content=render(
        "aml/list.html",
        **ctx,
        items=items,
        page=page,
        total=total,
        pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        q=q or "",
        preferred_filter=preferred or "",
    ))


@router.get("/new", response_class=HTMLResponse)
def aml_new_form(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show AML creation form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render("aml/new.html", **ctx))


@router.get("/{item_id}", response_class=HTMLResponse)
def aml_detail(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    """Show AML detail."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(ApprovedManufacturer).filter(ApprovedManufacturer.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render("aml/detail.html", **ctx, item=item))


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def aml_edit_form(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show AML edit form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(ApprovedManufacturer).filter(ApprovedManufacturer.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render("aml/edit.html", **ctx, item=item))


@router.post("/{item_id}/edit", response_class=HTMLResponse)
def aml_edit_submit(
    request: Request,
    item_id: int,
    manufacturer_name: str = Form(...),
    manufacturer_part_number: str = Form(""),
    preferred_flag: str = Form("No"),
    lead_time_days: int = Form(0),
    unit_cost: float = Form(0.0),
    compliance_status: str = Form(""),
    quality_rating: str = Form(""),
    notes: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Update AML entry."""
    user = require_user(request, db)
    item = db.query(ApprovedManufacturer).filter(ApprovedManufacturer.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    item.manufacturer_name = manufacturer_name
    item.manufacturer_part_number = manufacturer_part_number or None
    item.preferred_flag = preferred_flag or "No"
    item.lead_time_days = lead_time_days or None
    item.unit_cost = unit_cost or None
    item.compliance_status = compliance_status or None
    item.quality_rating = quality_rating or None
    item.notes = notes or None
    db.commit()
    return RedirectResponse(url=f"/aml/{item_id}", status_code=303)


@router.post("/new", response_class=HTMLResponse)
def aml_new_submit(
    request: Request,
    part_number: str = Form(...),
    manufacturer_name: str = Form(...),
    manufacturer_part_number: str = Form(""),
    source_type: str = Form("DIRECT"),
    preferred_flag: str = Form("No"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Create new AML entry."""
    user = require_user(request, db)
    item = ApprovedManufacturer(
        part_number=part_number,
        number=next_object_id(db, "aml", user.tenant_key if user else None),
        manufacturer_name=manufacturer_name,
        manufacturer_part_number=manufacturer_part_number or None,
        source_type=source_type,
        preferred_flag=preferred_flag or "No",
        tenant_id=1,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/aml/{item.id}", status_code=303)


@router.post("/{item_id}/delete", response_class=HTMLResponse)
def aml_delete(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Delete an AML entry and redirect to the list."""
    user = require_user(request, db)
    item = db.query(ApprovedManufacturer).filter(ApprovedManufacturer.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/aml", status_code=303)