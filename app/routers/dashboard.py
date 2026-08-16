"""Dashboard router — summary stats and overview."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse

from app.database import TenantScopedSession
from app.models import Part, BomItem, CostingBomItem, EngineeringChangeOrder, ApprovedManufacturer, ApprovedVendor, CadMetadata, Document, Favorite
from app.routers.auth import require_user, auth_context, get_tenant_db, get_settings
from app.template_utils import render

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Render the dashboard with summary statistics."""
    # Require login
    user = require_user(request, db)
    ctx = auth_context(request, db)

    # Use subquery approach to ensure tenant scoping works with count/sum functions
    part_count = (
        db.query(func.count(Part.part_number))
        .filter(Part.tenant_key == user.tenant_key)
        .scalar()
    ) or 0
    bom_count = (
        db.query(func.count(BomItem.id))
        .filter(BomItem.tenant_key == user.tenant_key)
        .scalar()
    ) or 0
    costing_count = (
        db.query(func.count(CostingBomItem.id))
        .filter(CostingBomItem.tenant_key == user.tenant_key)
        .scalar()
    ) or 0
    eco_count = (
        db.query(func.count(EngineeringChangeOrder.eco_number))
        .filter(EngineeringChangeOrder.tenant_key == user.tenant_key)
        .scalar()
    ) or 0
    aml_count = (
        db.query(func.count(ApprovedManufacturer.id))
        .filter(ApprovedManufacturer.tenant_key == user.tenant_key)
        .scalar()
    ) or 0
    avl_count = (
        db.query(func.count(ApprovedVendor.id))
        .filter(ApprovedVendor.tenant_key == user.tenant_key)
        .scalar()
    ) or 0
    cad_count = (
        db.query(func.count(CadMetadata.id))
        .filter(CadMetadata.tenant_key == user.tenant_key)
        .scalar()
    ) or 0
    document_count = (
        db.query(func.count(Document.id))
        .filter(Document.tenant_key == user.tenant_key)
        .scalar()
    ) or 0

    # Status breakdown for parts
    status_breakdown = dict(
        db.query(Part.status, func.count(Part.part_number))
        .group_by(Part.status)
        .all()
    )

    # ECO status breakdown
    eco_status = dict(
        db.query(EngineeringChangeOrder.eco_status, func.count(EngineeringChangeOrder.eco_number))
        .group_by(EngineeringChangeOrder.eco_status)
        .all()
    )

    # Cost summary stats
    total_cost = (
        db.query(func.sum(CostingBomItem.rolled_total))
        .filter(CostingBomItem.level == 0, CostingBomItem.tenant_key == user.tenant_key)
        .scalar()
    ) or 0

    # Get user's favorites
    favorites = db.query(Favorite).filter(Favorite.user_id == user.user_id).all()

    # Enrich favorites with object details
    enriched_favorites = []
    for fav in favorites:
        detail = None
        if fav.object_type == "part":
            part = db.query(Part).filter(Part.part_number == fav.object_id).first()
            if part:
                detail = {"name": part.part_name, "url": f"/parts/{part.part_number}"}
        elif fav.object_type == "document":
            doc = db.query(Document).filter(Document.id == int(fav.object_id)).first()
            if doc:
                detail = {"name": doc.title or doc.name, "url": f"/documents/{doc.id}"}
        elif fav.object_type == "eco":
            eco = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == fav.object_id).first()
            if eco:
                detail = {"name": eco.eco_title, "url": f"/eco/{eco.eco_number}"}

        if detail:
            enriched_favorites.append({
                "object_type": fav.object_type,
                "object_id": fav.object_id,
                "name": detail["name"],
                "url": detail["url"],
                "created_date": fav.created_date,
            })

    return HTMLResponse(content=render(
        "dashboard.html",
        **ctx,
        part_count=part_count,
        bom_count=bom_count,
        costing_count=costing_count,
        eco_count=eco_count,
        aml_count=aml_count,
        avl_count=avl_count,
        cad_count=cad_count,
        document_count=document_count,
        status_breakdown=status_breakdown,
        eco_status=eco_status,
        total_cost=total_cost,
        statuses=get_settings(request).PART_STATUSES,
        eco_statuses=get_settings(request).ECO_STATUSES,
        favorites=enriched_favorites,
    ))


@router.get("/help", response_class=HTMLResponse, include_in_schema=False)
def help_page(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Render the help page with status legend."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "help.html",
        **ctx,
    ))
