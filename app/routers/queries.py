"""FastAPI router for the Query & Report system.

Endpoints (prefix /queries):
    GET  ""                  → guided builder page + saved-reports sidebar
    POST "/run"              → run guided builder query → results grid
    POST "/run-sql"          → run advanced read-only SQL → results grid
    POST "/save"             → save current definition as a report
    GET  "/saved"            → list saved reports
    GET  "/saved/{id}"       → re-run a saved report, show results
    POST "/saved/{id}/delete"→ delete a report (owner/admin)
    GET  "/saved/{id}/export"→ download exported results (csv|json)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import TenantScopedSession
from app.routers.auth import require_user, require_superuser, is_superuser, auth_context, get_tenant_db
from app.template_utils import render
from app.config import QUERY_MAX_ROWS

from app.queries.registry import list_entities, get_fields, get_model, OPERATORS
from app.queries.builder import build_guided, BuildError
from app.queries.runner import run_readonly, SqlValidationError
from app.queries.reports import (
    save_query,
    list_reports,
    get_query,
    delete_query,
    run_saved,
    export_results,
    safe_filename,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/queries", tags=["queries"])


# ── Helpers ──────────────────────────────────────────────────────

def _form_getlist(form, key: str) -> list:
    """Return list of values for a key from a Starlette FormData."""
    if hasattr(form, 'getlist'):
        return [v for v in form.getlist(key) if v]
    val = form.get(key)
    if isinstance(val, list):
        return [v for v in val if v]
    return [val] if val else []


def _parse_filters(form: dict) -> list[dict]:
    """Collect dynamic filter rows from the submitted form.

    Form keys: filter_count, filter_field_N, filter_op_N, filter_value_N.
    """
    filters = []
    try:
        count = int(form.get("filter_count", "0") or "0")
    except ValueError:
        count = 0
    for i in range(count):
        field = (form.get(f"filter_field_{i}") or "").strip()
        op = (form.get(f"filter_op_{i}") or "").strip()
        value = form.get(f"filter_value_{i}", "")
        if field and op:
            filters.append({"field": field, "op": op, "value": value})
    return filters


def _pagination(base_path: str, page: int, has_more: bool, extra: dict) -> dict:
    q = "&".join(f"{k}={v}" for k, v in extra.items() if v)
    prev_url = f"{base_path}?page={page-1}&{q}" if page > 1 else None
    next_url = f"{base_path}?page={page+1}&{q}" if has_more else None
    return {
        "page": page,
        "has_prev": page > 1,
        "has_next": has_more,
        "prev_url": prev_url,
        "next_url": next_url,
    }


# ── Builder page ────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def queries_page(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)

    saved = list_reports(db, user)
    entities = list_entities()

    return HTMLResponse(content=render(
        "queries/builder.html",
        **ctx,
        entities=entities,
        saved_reports=saved,
        result=None,
        current_entity=None,
        error=None,
    ))


# ── Guided run ──────────────────────────────────────────────────

@router.post("/run", response_class=HTMLResponse)
async def run_guided(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    form = await request.form()

    entity = (form.get("entity") or "").strip()
    columns = _form_getlist(form, "columns")

    filters = _parse_filters(form)
    sort = (form.get("sort") or "").strip() or None
    sort_dir = (form.get("sort_dir") or "asc").strip()
    try:
        limit = int(form.get("limit") or QUERY_MAX_ROWS)
    except ValueError:
        limit = QUERY_MAX_ROWS
    limit = min(max(limit, 1), QUERY_MAX_ROWS)

    try:
        page = max(int(form.get("page") or 1), 1)
    except ValueError:
        page = 1
    offset = (page - 1) * limit

    error = None
    result = None
    try:
        stmt, sql_str, params = build_guided(
            entity_key=entity,
            columns=columns or None,
            filters=filters,
            sort=sort,
            sort_dir=sort_dir,
            limit=limit + 1,  # fetch one extra to detect "next"
            offset=offset,
            user=user,
        )
        res = db.execute(stmt)
        all_rows = res.fetchall()
        cols = list(res.keys())
        has_more = len(all_rows) > limit
        rows = [list(r) for r in all_rows[:limit]]
        result = {
            "mode": "guided",
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
            "truncated": False,
            "sql": sql_str,
            "entity": entity,
        }
    except (BuildError, ValueError) as e:
        error = str(e)
    except Exception as e:
        logger.exception("Guided run failed")
        error = f"Query error: {e}"

    saved = list_reports(db, user)
    entities = list_entities()
    pagination = _pagination("/queries/run", page, has_more if result else False, {"entity": entity})

    return HTMLResponse(content=render(
        "queries/builder.html",
        **ctx,
        entities=entities,
        saved_reports=saved,
        result=result,
        error=error,
        current_entity=entity,
        fields=get_fields(get_model(entity)) if get_model(entity) else [],
        op_labels={k: v[0] for k, v in OPERATORS.items()},
        filters=filters,
        columns_selected=columns,
        sort=sort or "",
        sort_dir=sort_dir,
        limit=limit,
        pagination=pagination,
    ))


# ── Advanced SQL run ────────────────────────────────────────────

@router.post("/run-sql", response_class=HTMLResponse)
async def run_sql(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)

    form = await request.form()
    sql = (form.get("sql") or "").strip()

    error = None
    result = None
    try:
        result = run_readonly(sql, tenant=getattr(request.state, "tenant", None))
    except SqlValidationError as e:
        error = str(e)
    except Exception as e:
        logger.exception("SQL run failed")
        error = f"Query error: {e}"

    saved = list_reports(db, user)
    entities = list_entities()

    return HTMLResponse(content=render(
        "queries/builder.html",
        **ctx,
        entities=entities,
        saved_reports=saved,
        result=result,
        error=error,
        current_entity=None,
        sql_box=sql,
        active_tab="sql",
    ))


# ── Save report ─────────────────────────────────────────────────

@router.post("/save", response_class=HTMLResponse)
async def save_report(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    form = await request.form()

    if not is_superuser(user):
        saved = list_reports(db, user)
        entities = list_entities()
        mode = (form.get("mode") or "guided").strip()
        entity = (form.get("entity") or "").strip()
        try:
            limit = int(form.get("limit") or QUERY_MAX_ROWS)
        except ValueError:
            limit = QUERY_MAX_ROWS
        return HTMLResponse(content=render(
            "queries/builder.html",
            **ctx,
            entities=entities,
            saved_reports=saved,
            result=None,
            error="Only the masteradmin may perform this action.",
            current_entity=entity if mode == "guided" else None,
            fields=get_fields(get_model(entity)) if mode == "guided" and get_model(entity) else [],
            filters=_parse_filters(form) if mode == "guided" else [],
            columns_selected=_form_getlist(form, "columns") if mode == "guided" else [],
            sort=(form.get("sort") or "").strip() or None,
            sort_dir=(form.get("sort_dir") or "asc").strip(),
            limit=limit,
            sql_box=form.get("sql") if mode == "sql" else None,
            active_tab="sql" if mode == "sql" else None,
            op_labels={k: v[0] for k, v in OPERATORS.items()},
        ))
    name = (form.get("report_name") or "").strip()
    description = (form.get("report_description") or "").strip()
    mode = (form.get("mode") or "guided").strip()
    is_public = form.get("is_public") == "on"

    error = None
    if mode == "sql":
        definition = (form.get("sql") or "").strip()
    else:
        entity = (form.get("entity") or "").strip()
        columns = _form_getlist(form, "columns")
        filters = _parse_filters(form)
        sort = (form.get("sort") or "").strip() or None
        sort_dir = (form.get("sort_dir") or "asc").strip()
        try:
            limit = int(form.get("limit") or QUERY_MAX_ROWS)
        except ValueError:
            limit = QUERY_MAX_ROWS
        limit = min(max(limit, 1), QUERY_MAX_ROWS)
        definition = {
            "entity": entity,
            "columns": columns,
            "filters": filters,
            "sort": sort,
            "sort_dir": sort_dir,
            "limit": limit,
        }

    try:
        q = save_query(db, user, name, description, mode, definition, is_public)
        return RedirectResponse(url=f"/queries/saved/{q.id}", status_code=303)
    except Exception as e:
        error = str(e)

    saved = list_reports(db, user)
    entities = list_entities()
    return HTMLResponse(content=render(
        "queries/builder.html",
        **ctx,
        entities=entities,
        saved_reports=saved,
        result=None,
        error=error,
        current_entity=(definition.get("entity") if isinstance(definition, dict) else None),
        sql_box=(definition if isinstance(definition, str) else ""),
    ))


# ── List saved reports ──────────────────────────────────────────

@router.get("/saved", response_class=HTMLResponse)
async def saved_list(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    saved = list_reports(db, user)
    return HTMLResponse(content=render(
        "queries/saved.html",
        **ctx,
        saved_reports=saved,
    ))


# ── Run a saved report ──────────────────────────────────────────

@router.get("/saved/{query_id}", response_class=HTMLResponse)
async def saved_run(query_id: int, request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    ctx = auth_context(request, db)

    q = get_query(db, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    error = None
    result = None
    try:
        result = run_saved(db, user, q, tenant=getattr(request.state, "tenant", None))
    except (BuildError, SqlValidationError, PermissionError, ValueError) as e:
        error = str(e)
    except Exception as e:
        logger.exception("Saved run failed")
        error = f"Query error: {e}"

    return HTMLResponse(content=render(
        "queries/result.html",
        **ctx,
        report=q,
        result=result,
        error=error,
    ))


# ── Delete a saved report ───────────────────────────────────────

@router.post("/saved/{query_id}/delete", response_class=HTMLResponse)
async def saved_delete(query_id: int, request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    user = require_user(request, db)
    q = get_query(db, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    try:
        delete_query(db, user, q)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return RedirectResponse(url="/queries/saved", status_code=303)


# ── Export a saved report ───────────────────────────────────────

@router.get("/saved/{query_id}/export")
async def saved_export(
    query_id: int,
    format: str = "csv",
    request: Request = None,
    db: TenantScopedSession = Depends(get_tenant_db),
):
    user = require_user(request, db)
    q = get_query(db, query_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    try:
        result = run_saved(db, user, q, limit=QUERY_MAX_ROWS, tenant=getattr(request.state, "tenant", None))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to run report: {e}")

    contents, media = export_results(result, format, q.name)
    filename = safe_filename(q.name, format if format in ("csv", "json") else "csv")
    return StreamingResponse(
        iter([contents]),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
