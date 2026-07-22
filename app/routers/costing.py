"""Costing BOM router."""

from typing import Optional, Dict
from fastapi import APIRouter, Depends, Query, Form, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse

from app.database import get_db
from app.models import CostingBomItem, User
from app.config import DEFAULT_PAGE_SIZE
from app.routers.auth import require_user, require_role, auth_context
from app.template_utils import render

router = APIRouter(prefix="/costing")


@router.get("", response_class=HTMLResponse)
def list_costing(
    request: Request,
    q: Optional[str] = Query(None, description="Search by part number or name"),
    cost_type: Optional[str] = Query(None, description="Filter by cost type"),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """List costing BOM items."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    query = db.query(CostingBomItem)

    if q:
        query = query.filter(
            or_(
                CostingBomItem.part_number.ilike(f"%{q}%"),
                CostingBomItem.part_name.ilike(f"%{q}%"),
            )
        )
    if cost_type:
        query = query.filter(CostingBomItem.cost_type == cost_type)

    total = query.count()
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    items = query.order_by(CostingBomItem.level, CostingBomItem.part_number).offset(offset).limit(DEFAULT_PAGE_SIZE).all()

    return HTMLResponse(content=render(
        "costing/list.html",
        **ctx,
        items=items,
        page=page,
        total=total,
        pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        q=q or "",
        cost_type_filter=cost_type or "",
    ))


@router.get("/new", response_class=HTMLResponse)
def costing_new_form(
    request: Request,
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show costing item creation form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render("costing/new.html", **ctx))


@router.get("/{item_id}", response_class=HTMLResponse)
def costing_detail(request: Request, item_id: int, db: Session = Depends(get_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(CostingBomItem).filter(CostingBomItem.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render("costing/detail.html", **ctx, item=item))


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def costing_edit_form(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(CostingBomItem).filter(CostingBomItem.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render("costing/edit.html", **ctx, item=item))


@router.post("/{item_id}/edit", response_class=HTMLResponse)
def costing_edit_submit(
    request: Request,
    item_id: int,
    material_cost: float = Form(0.0),
    labor_cost: float = Form(0.0),
    overhead_cost: float = Form(0.0),
    machining_cost: float = Form(0.0),
    unit_cost: float = Form(0.0),
    extended_cost: float = Form(0.0),
    rolled_total: float = Form(0.0),
    cost_type: str = Form("LEAF"),
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    item = db.query(CostingBomItem).filter(CostingBomItem.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    item.material_cost = material_cost
    item.labor_cost = labor_cost
    item.overhead_cost = overhead_cost
    item.machining_cost = machining_cost
    item.unit_cost = unit_cost
    item.extended_cost = extended_cost
    item.rolled_total = rolled_total
    item.cost_type = cost_type or "LEAF"
    db.commit()
    return RedirectResponse(url=f"/costing/{item_id}", status_code=303)


@router.post("/new", response_class=HTMLResponse)
def costing_new_submit(
    request: Request,
    part_number: str = Form(...),
    part_name: str = Form(""),
    level: int = Form(0),
    qty: int = Form(1),
    material_cost: float = Form(0.0),
    labor_cost: float = Form(0.0),
    overhead_cost: float = Form(0.0),
    machining_cost: float = Form(0.0),
    unit_cost: float = Form(0.0),
    cost_type: str = Form("LEAF"),
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    item = CostingBomItem(
        part_number=part_number,
        part_name=part_name or None,
        level=level,
        qty=qty,
        material_cost=material_cost,
        labor_cost=labor_cost,
        overhead_cost=overhead_cost,
        machining_cost=machining_cost,
        unit_cost=unit_cost,
        extended_cost=unit_cost * qty,
        rolled_total=unit_cost * qty,
        cost_type=cost_type or "LEAF",
        tenant_id=1,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/costing/{item.id}", status_code=303)


@router.post("/{item_id}/delete", response_class=HTMLResponse)
def costing_delete(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
    _role: User = Depends(require_role(["author"])),
):
    """Delete a costing item and redirect to the list."""
    user = require_user(request, db)
    item = db.query(CostingBomItem).filter(CostingBomItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/costing", status_code=303)
