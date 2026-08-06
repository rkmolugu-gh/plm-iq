"""FastAPI router for search — server-rendered UI + JSON API.

Summary:
    Provides two endpoints:
    1. GET /search  — SSR search page with BM25/RAG mode toggle,
       entity filter, results display, RAG answer box, and timing telemetry.
    2. GET /search/api — JSON endpoint for programmatic/async access.

    Multimodal search:
        When uploading an image in RAG mode, the image is sent to a vision-
        capable LLM alongside search context for multimodal answers.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request, Depends, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from .search import search, ENTITY_LABELS
from .ragai import rag_answer, rag_answer_multimodal
from .config import SEARCH_DEFAULT_SIZE, MAX_UPLOAD_SIZE
from .vision import prepare_image, ImageValidationError
from app.database import get_db
from app.routers.auth import require_user, auth_context
from app.template_utils import render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


@router.get("", response_class=HTMLResponse)
def search_page(
    request: Request,
    q: Optional[str] = Query(None, description="Search query"),
    mode: str = Query("bm25", description="Search mode: bm25 or rag"),
    entity: Optional[str] = Query(None, description="Entity type filter"),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Server-rendered search page.

    When a query (q) is provided, executes the search and renders results.
    Without a query, shows the empty search form.
    """
    user = require_user(request, db)
    ctx = auth_context(request, db)
    tenant_id = user.tenant_id if user else None  # Resolve tenant from current user
    logger.info(f"Search page: q='{q}' mode={mode} entity={entity} page={page} tenant={tenant_id}")

    result = None
    if q:
        if mode == "rag":
            result = rag_answer(query=q, entity_type=entity, tenant_id=tenant_id)
        else:
            # BM25 or hybrid mode — use the search() function
            result = search(
                query=q,
                mode=mode,
                entity_type=entity,
                page=page,
                size=SEARCH_DEFAULT_SIZE,
                tenant_id=tenant_id,
            )

    return HTMLResponse(content=render(
        "search.html",
        **ctx,
        result=result,
        q=q or "",
        mode=mode,
        entity_filter=entity or "",
        entity_labels=ENTITY_LABELS,
    ))


@router.post("/multimodal", response_class=HTMLResponse)
async def search_multimodal(
    request: Request,
    q: str = Form("", description="Search query"),
    files: list[UploadFile] = File(default=[], description="Optional image attachments"),
    db: Session = Depends(get_db),
):
    """Multimodal search — accepts text query + image uploads for vision LLM.

    When images are provided, they are processed by the vision module and
    sent alongside search context to a vision-capable LLM. Without images,
    falls back to standard RAG.
    """
    user = require_user(request, db)
    ctx = auth_context(request, db)
    tenant_id = ctx.get("tenant_id")  # Resolve tenant from auth context
    logger.info(f"Search multimodal: q='{q}' files={len(files)} tenant={tenant_id}")

    # Process uploaded images
    images = []
    for f in files:
        if f.filename and f.content_type in _ALLOWED_IMAGE_TYPES:
            raw = await f.read()
            try:
                prepared = prepare_image(
                    raw=raw,
                    filename=f.filename,
                    max_size_bytes=MAX_UPLOAD_SIZE,
                )
                images.append(prepared)
            except ImageValidationError as e:
                logger.warning(f"Image validation failed for {f.filename}: {e}")
            except Exception as e:
                logger.warning(f"Image processing failed for {f.filename}: {e}")

    if images:
        result = rag_answer_multimodal(query=q or "", images=images, entity_type=None, tenant_id=tenant_id)
    else:
        result = rag_answer(query=q or "", entity_type=None, tenant_id=tenant_id)

    return HTMLResponse(content=render(
        "search.html",
        **ctx,
        result=result,
        q=q or "",
        mode="rag",
        entity_filter="",
        entity_labels=ENTITY_LABELS,
    ))


@router.get("/api")
def search_api(
    request: Request,
    q: str = Query(..., description="Search query"),
    mode: str = Query("bm25", description="Search mode: bm25 or rag"),
    entity: Optional[str] = Query(None, description="Entity type filter"),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """JSON API endpoint for search.

    Returns structured results suitable for async/JS consumption.
    Response format:
        { "results": [...], "total": N, "page": N, "pages": N,
          "query": "...", "search_mode": "...", "timing": {...},
          "answer": "..." (only in RAG mode), "citations": [...] (only in RAG mode) }
    """
    # Require login for API too
    user = require_user(request, db)
    ctx = auth_context(request, db)
    tenant_id = ctx.get("tenant_id")  # Resolve tenant from auth context
    logger.info(f"Search API: q='{q}' mode={mode} entity={entity} page={page} tenant={tenant_id}")

    if mode == "rag":
        result = rag_answer(query=q, entity_type=entity, tenant_id=tenant_id)
    else:
        # BM25 or hybrid mode — use the search() function
        result = search(
            query=q,
            mode=mode,
            entity_type=entity,
            page=page,
            size=SEARCH_DEFAULT_SIZE,
            tenant_id=tenant_id,
        )

    return JSONResponse(content=result)
