"""
Favorites router — add/remove favorites and list them for the dashboard.

Enforces a limit of 5 favorites per user per object type.
"""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.database import TenantScopedSession
from app.models import Favorite, Part, Document, EngineeringChangeOrder
from app.routers.auth import require_user, auth_context, get_tenant_db
from app.template_utils import render

router = APIRouter(prefix="/favorites", tags=["favorites"])

MAX_FAVORITES_PER_TYPE = 5


@router.post("/add")
async def add_favorite(
    request: Request,
    object_type: str = Form(...),
    object_id: str = Form(...),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Add an object to the user's favorites."""
    ctx = auth_context(request, db)
    user = ctx["current_user"]
    tenant_id = ctx["current_tenant"].tenant_id

    # Check if already favorited
    existing = (
        db.query(Favorite)
        .filter(
            Favorite.user_id == user.user_id,
            Favorite.object_type == object_type,
            Favorite.object_id == object_id,
        )
        .first()
    )
    if existing:
        return RedirectResponse(
            url=request.headers.get("referer", "/dashboard"), status_code=303
        )

    # Check limit (5 per user per object type)
    count = (
        db.query(Favorite)
        .filter(
            Favorite.user_id == user.user_id,
            Favorite.object_type == object_type,
        )
        .count()
    )
    if count >= MAX_FAVORITES_PER_TYPE:
        # Could add a flash message here
        return RedirectResponse(
            url=request.headers.get("referer", "/dashboard"), status_code=303
        )

    # Create favorite
    favorite = Favorite(
        user_id=user.user_id,
        object_type=object_type,
        object_id=object_id,
        tenant_id=tenant_id,
    )
    db.add(favorite)
    db.commit()

    return RedirectResponse(
        url=request.headers.get("referer", "/dashboard"), status_code=303
    )


@router.post("/remove")
async def remove_favorite(
    request: Request,
    object_type: str = Form(...),
    object_id: str = Form(...),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Remove an object from the user's favorites."""
    ctx = auth_context(request, db)
    user = ctx["current_user"]

    favorite = (
        db.query(Favorite)
        .filter(
            Favorite.user_id == user.user_id,
            Favorite.object_type == object_type,
            Favorite.object_id == object_id,
        )
        .first()
    )
    if favorite:
        db.delete(favorite)
        db.commit()

    return RedirectResponse(
        url=request.headers.get("referer", "/dashboard"), status_code=303
    )


@router.get("", response_class=HTMLResponse)
async def list_favorites(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """List the current user's favorites (for the dashboard)."""
    ctx = auth_context(request, db)
    user = ctx["current_user"]

    favorites = (
        db.query(Favorite)
        .filter(Favorite.user_id == user.user_id)
        .order_by(Favorite.created_date.desc())
        .all()
    )

    # Enrich favorites with object details
    enriched = []
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
            eco = (
                db.query(EngineeringChangeOrder)
                .filter(EngineeringChangeOrder.eco_number == fav.object_id)
                .first()
            )
            if eco:
                detail = {"name": eco.eco_title, "url": f"/eco/{eco.eco_number}"}

        if detail:
            enriched.append(
                {
                    "id": fav.id,
                    "object_type": fav.object_type,
                    "object_id": fav.object_id,
                    "created_date": fav.created_date,
                    "name": detail["name"],
                    "url": detail["url"],
                }
            )

    return HTMLResponse(content=render(
        "favorites/list.html",
        **ctx, favorites=enriched, max_favorites=MAX_FAVORITES_PER_TYPE,
    ))


def get_user_favorites(user_id: int, db: Session) -> list[dict]:
    """Helper function to get user favorites for dashboard display."""
    favorites = (
        db.query(Favorite)
        .filter(Favorite.user_id == user_id)
        .order_by(Favorite.object_type, Favorite.created_date.desc())
        .all()
    )

    enriched = []
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
            eco = (
                db.query(EngineeringChangeOrder)
                .filter(EngineeringChangeOrder.eco_number == fav.object_id)
                .first()
            )
            if eco:
                detail = {"name": eco.eco_title, "url": f"/eco/{eco.eco_number}"}

        if detail:
            enriched.append(
                {
                    "object_type": fav.object_type,
                    "object_id": fav.object_id,
                    "name": detail["name"],
                    "url": detail["url"],
                }
            )

    return enriched
