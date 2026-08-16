"""Dashboard router — PLM News (company activity feed)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.activity import get_company_activity
from app.database import TenantScopedSession
from app.routers.auth import require_user, auth_context, get_tenant_db, get_settings
from app.template_utils import render

router = APIRouter()


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def plm_news(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Render the PLM News page with company-wide activity."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    activity = get_company_activity(request, db, get_settings(request))

    return HTMLResponse(content=render(
        "plm_news.html",
        **ctx,
        **activity,
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
