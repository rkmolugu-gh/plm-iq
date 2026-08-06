"""AVL router."""

from typing import Optional, Dict
from fastapi import APIRouter, Depends, Query, Form, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import TenantScopedSession
from app.models import ApprovedVendor, User
from app.config import DEFAULT_PAGE_SIZE
from app.routers.auth import require_user, require_role, auth_context, get_tenant_db
from app.template_utils import render

router = APIRouter(prefix="/avl")


@router.get("", response_class=HTMLResponse)
def list_avl(
    request: Request,
    q: Optional[str] = Query(None, description="Search"),
    preferred: Optional[str] = Query(None, description="Preferred only"),
    page: int = Query(1, ge=1),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """List approved vendors."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    query = db.query(ApprovedVendor)

    if q:
        query = query.filter(
            or_(
                ApprovedVendor.part_number.ilike(f"%{q}%"),
                ApprovedVendor.vendor_name.ilike(f"%{q}%"),
            )
        )
    if preferred == "Yes":
        query = query.filter(ApprovedVendor.preferred_flag == "Yes")

    total = query.count()
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    items = query.order_by(ApprovedVendor.part_number).offset(offset).limit(DEFAULT_PAGE_SIZE).all()

    return HTMLResponse(content=render(
        "avl/list.html",
        **ctx,
        items=items,
        page=page,
        total=total,
        pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        q=q or "",
        preferred_filter=preferred or "",
    ))


@router.get("/new", response_class=HTMLResponse)
def avl_new_form(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show AVL creation form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render("avl/new.html", **ctx))


@router.get("/{item_id}", response_class=HTMLResponse)
def avl_detail(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(ApprovedVendor).filter(ApprovedVendor.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render("avl/detail.html", **ctx, item=item))


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def avl_edit_form(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(ApprovedVendor).filter(ApprovedVendor.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render("avl/edit.html", **ctx, item=item))


@router.post("/{item_id}/edit", response_class=HTMLResponse)
def avl_edit_submit(
    request: Request,
    item_id: int,
    vendor_name: str = Form(...),
    vendor_part_number: str = Form(""),
    preferred_flag: str = Form("No"),
    unit_price: float = Form(0.0),
    min_order_qty: int = Form(1),
    lead_time_days: int = Form(0),
    iso_certified: str = Form(""),
    payment_terms: str = Form(""),
    notes: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    item = db.query(ApprovedVendor).filter(ApprovedVendor.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    item.vendor_name = vendor_name
    item.vendor_part_number = vendor_part_number or None
    item.preferred_flag = preferred_flag or "No"
    item.unit_price = unit_price or None
    item.min_order_qty = min_order_qty or None
    item.lead_time_days = lead_time_days or None
    item.iso_certified = iso_certified or None
    item.payment_terms = payment_terms or None
    item.notes = notes or None
    db.commit()
    return RedirectResponse(url=f"/avl/{item_id}", status_code=303)


@router.post("/new", response_class=HTMLResponse)
def avl_new_submit(
    request: Request,
    part_number: str = Form(...),
    vendor_name: str = Form(...),
    vendor_part_number: str = Form(""),
    preferred_flag: str = Form("No"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    item = ApprovedVendor(
        part_number=part_number,
        vendor_name=vendor_name,
        vendor_part_number=vendor_part_number or None,
        preferred_flag=preferred_flag or "No",
        tenant_id=1,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/avl/{item.id}", status_code=303)


@router.post("/{item_id}/delete", response_class=HTMLResponse)
def avl_delete(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Delete an AVL entry and redirect to the list."""
    user = require_user(request, db)
    item = db.query(ApprovedVendor).filter(ApprovedVendor.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/avl", status_code=303)