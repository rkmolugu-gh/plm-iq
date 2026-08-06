"""CSV import router — unified /import page for all business objects."""

import csv
import io
from typing import List

from fastapi import APIRouter, Depends, Form, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.database import TenantScopedSession
from app.models import Tenant, User
from app.routers.auth import require_user, require_role, auth_context, get_tenant_db
from app.template_utils import render
from app.import_core import (
    ENTITY_CONFIG,
    ENTITY_ORDER,
    run_import,
    template_header,
)

router = APIRouter()


def _entities() -> List[tuple]:
    return [(k, ENTITY_CONFIG[k]["label"]) for k in ENTITY_ORDER]


@router.get("/import", response_class=HTMLResponse)
def import_page(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show the unified CSV import form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "import/import.html", **ctx,
        entities=_entities(), result=None,
    ))


@router.post("/import", response_class=HTMLResponse)
async def import_upload(
    request: Request,
    entity: str = Form(...),
    file: UploadFile = File(...),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Parse an uploaded CSV and upsert its rows for the chosen entity."""
    user = require_user(request, db)
    ctx = auth_context(request, db)

    try:
        raw = await file.read()
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        result = {"entity": entity, "inserted": 0, "updated": 0,
                  "rejected": [], "warnings": [],
                  "error": "File is not valid UTF-8 text. Please upload a CSV (UTF-8)."}
        return HTMLResponse(content=render(
            "import/import.html", **ctx,
            entities=_entities(), result=result,
        ))

    rows = list(csv.DictReader(io.StringIO(text)))

    default_tenant = ctx.get("current_tenant")
    default_tenant_id = default_tenant.tenant_id if default_tenant else 1

    result = run_import(entity, rows, db, default_tenant_id=default_tenant_id)
    return HTMLResponse(content=render(
        "import/import.html", **ctx,
        entities=_entities(), result=result,
    ))


@router.get("/import/template", response_class=PlainTextResponse)
def import_template(
    request: Request,
    entity: str = Query(...),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Return a starter CSV header row for the chosen entity."""
    require_user(request, db)
    if entity not in ENTITY_CONFIG:
        return PlainTextResponse(f"Unknown entity '{entity}'.", status_code=404)
    return PlainTextResponse(template_header(entity), media_type="text/csv")
