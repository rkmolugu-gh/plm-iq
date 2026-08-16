"""FastAPI router for PLM Assistant — conversational agent with tool calling and multimodal support.

The PLM Assistant is a goal-driven engineering agent that:
  - Answers PLM questions using tool calls (get_part, create_part)
  - Supports image uploads for vision-capable LLMs
  - Maintains conversation history per session
  - Uses the ReAct pattern (Thought → Action → Observation → Answer)

Endpoints:
  1. GET  /assistant     — renders the assistant chat page with session history
  2. POST /assistant     — sends a message with optional file attachments, runs agent, redirects to GET
  3. POST /assistant/new — clears the current session's history and uploaded files
"""

import base64
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, UploadFile, File, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.aisearch.vision import prepare_image
from app.database import get_db, TenantScopedSession
from app.routers.auth import require_user, auth_context, get_tenant_key
from app.template_utils import render

from .config import ASSISTANT_MODEL, MAX_UPLOAD_SIZE, MAX_HISTORY_TURNS, MAX_SESSIONS
from .assistant_agent import assistant_chat, prepare_assistant_messages
from .impact_agent import impact_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# ── In-memory session store ──────────────────────────────────────
sessions: dict[str, dict] = {}

# ── Upload config ────────────────────────────────────────────────
_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

_MODE_COOKIE = "ai_mode"
_SESSION_COOKIES = {"assistant": "assistant_session", "impact": "impact_session"}
_MODES = ("assistant", "impact")


def _session_key(mode: str, session_id: str) -> str:
    return f"{mode}:{session_id}"


def _resolve_mode(request: Request) -> str:
    """Mode from query first, then the persisted ai_mode cookie, else default."""
    q = request.query_params.get("mode")
    if q and q in _MODES:
        return q
    return request.cookies.get(_MODE_COOKIE) or "assistant"


# ── Helpers ──────────────────────────────────────────────────────

def _cleanup_uploads(session_id: str) -> None:
    """Remove the per-session upload directory and all its contents."""
    d = _UPLOAD_DIR / session_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def _extract_pdf_text(raw: bytes) -> str:
    """Extract text from a PDF byte stream using pypdf."""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(raw))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
        return "\n\n".join(pages) if pages else "[PDF: no extractable text]"
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return f"[PDF: extraction error — {e}]"


def _process_uploaded_file(file: UploadFile, session_id: str) -> dict:
    """Process a single uploaded file — image, PDF, or text.

    Returns dict with keys: filename, content_type, size, type_hint,
    content, base64_data (images only).
    """
    content_type = file.content_type or "application/octet-stream"
    raw = file.file.read()
    size = len(raw)

    if size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File '{file.filename}' exceeds the {MAX_UPLOAD_SIZE // (1024 * 1024)} MB upload limit.",
        )

    metadata: dict = {
        "filename": file.filename or "unnamed",
        "content_type": content_type,
        "size": size,
        "size_display": _fmt_size(size),
    }

    # Image files — use vision module
    if content_type in _ALLOWED_IMAGE_TYPES:
        try:
            prepared = prepare_image(
                raw=raw,
                filename=file.filename or "image",
                max_size_bytes=MAX_UPLOAD_SIZE,
            )
            metadata["type_hint"] = "image"
            metadata["base64_data"] = prepared["base64_data"]
            metadata["content"] = f"[Image: {file.filename} ({prepared['size_display']})]"
        except Exception as e:
            logger.warning(f"Image processing failed for {file.filename}: {e}")
            b64 = base64.b64encode(raw).decode("utf-8")
            metadata["type_hint"] = "image"
            metadata["base64_data"] = f"data:{content_type};base64,{b64}"
            metadata["content"] = f"[Image: {file.filename} ({_fmt_size(size)})]"

    # PDF files
    elif content_type == "application/pdf":
        metadata["type_hint"] = "pdf"
        metadata["content"] = _extract_pdf_text(raw)

    # Text files
    elif content_type.startswith("text/"):
        metadata["type_hint"] = "text"
        metadata["content"] = raw.decode("utf-8", errors="replace")

    # Unsupported
    else:
        metadata["type_hint"] = "other"
        metadata["content"] = (
            f"[File: {file.filename} ({_fmt_size(size)}) — "
            f"unsupported format. Supported: PNG, JPG, GIF, WebP, PDF, TXT, CSV]"
        )

    return metadata


def _get_or_create_session(session_id: Optional[str], mode: str = "assistant") -> tuple[str, dict]:
    """Return (session_id, session_data) — creates a new session if needed.

    Sessions are namespaced by mode so the general assistant and the impact
    analysis agent keep separate conversations.
    """
    if not session_id or _session_key(mode, session_id) not in sessions:
        session_id = str(uuid.uuid4())
        sessions[_session_key(mode, session_id)] = {"messages": [], "flags": {}}
    return session_id, sessions[_session_key(mode, session_id)]


def _trim_history(session_data: dict) -> None:
    """Trim session to MAX_HISTORY_TURNS user+assistant pairs."""
    msgs = session_data.get("messages", [])
    max_msgs = MAX_HISTORY_TURNS * 2
    if len(msgs) > max_msgs:
        session_data["messages"] = msgs[-max_msgs:]


def _evict_if_needed() -> None:
    """Evict oldest session when count exceeds MAX_SESSIONS."""
    if len(sessions) > MAX_SESSIONS:
        oldest = next(iter(sessions))
        del sessions[oldest]


# ── Routes ───────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def assistant_page(request: Request, db: Session = Depends(get_db)):
    """Render the assistant chat page with session history.

    Supports an optional ?mode=impact query that switches the page (and its
    session) to the impact analysis agent. The mode is persisted in a cookie and
    carried by the forms as a hidden field so POST keeps the same mode.
    """
    user = require_user(request, db)
    ctx = auth_context(request, db)
    mode = _resolve_mode(request)
    cookie_name = _SESSION_COOKIES[mode]
    session_id, session_data = _get_or_create_session(
        request.cookies.get(cookie_name), mode=mode)
    messages = session_data["messages"]
    is_impact = mode == "impact"

    response = HTMLResponse(content=render(
        "assistant.html",
        messages=messages,
        **ctx,
        assistant_model=ASSISTANT_MODEL,
        mode=mode,
        is_impact=is_impact,
    ))
    response.set_cookie(key=cookie_name, value=session_id, max_age=3600, httponly=True)
    response.set_cookie(key=_MODE_COOKIE, value=mode, max_age=3600, httponly=True)
    return response


@router.post("", response_class=HTMLResponse)
async def assistant_send(
    request: Request,
    message: str = Form("", description="User's message"),
    files: list[UploadFile] = File(default=[], description="Optional file attachments"),
    mode: str = Form("assistant", description="Agent mode: 'assistant' or 'impact'"),
    db: Session = Depends(get_db),
):
    """Process a user message through the assistant or impact agent.

    The hidden 'mode' form field selects the agent: 'impact' runs the
    read-only impact analysis agent (no mutating tools), anything else runs the
    general assistant. Images trigger the vision path on the general assistant only;
    impact mode is text-only.
    """
    user = require_user(request, db)
    tenant_key = get_tenant_key(request, db)
    if mode not in _MODES:
        mode = _MODES[0]
    cookie_name = _SESSION_COOKIES[mode]
    session_id, session_data = _get_or_create_session(
        request.cookies.get(cookie_name), mode=mode)
    msgs = session_data["messages"]

    # 1. Process uploaded files
    uploaded_file_metas = []
    for f in files:
        if f.filename:
            meta = _process_uploaded_file(f, session_id)
            uploaded_file_metas.append(meta)

    # 2. Build user message content (multimodal where supported)
    user_content = prepare_assistant_messages(message, uploaded_file_metas)
    user_msg: dict = {"role": "user", "content": user_content}
    if uploaded_file_metas:
        user_msg["files"] = uploaded_file_metas
    if isinstance(user_content, list):
        display_text = message or " ".join(f"[{f['filename']}]" for f in uploaded_file_metas)
        user_msg["display_text"] = display_text
    msgs.append(user_msg)

    # 3. Call the agent for the active mode
    agent_messages = list(msgs)
    logger.info(f"[assistant] mode={mode} session={session_id[:8]} msg='{message[:80]}' files={len(uploaded_file_metas)}")
    try:
        if mode == "impact":
            reply = impact_chat(messages=agent_messages, tenant_key=tenant_key)
        else:
            reply = assistant_chat(messages=agent_messages, tenant_key=tenant_key)
    except Exception as e:
        logger.exception(f"[assistant] Agent call failed: {e}")
        error_msg = str(e)
        if error_msg.startswith("RuntimeError: "):
            error_msg = error_msg[len("RuntimeError: "):]
        reply = f"I'm sorry, I couldn't process that request. Error: {error_msg}"

    # 4. Store assistant reply
    assistant_msg: dict = {"role": "assistant", "content": reply}
    msgs.append(assistant_msg)

    # 5. Trim and evict
    _trim_history(session_data)
    _evict_if_needed()

    # 6. Redirect to GET (POST-Redirect-GET pattern), keeping the mode + session
    response = RedirectResponse(url=f"/assistant?mode={mode}", status_code=303)
    response.set_cookie(key=cookie_name, value=session_id, max_age=3600, httponly=True)
    response.set_cookie(key=_MODE_COOKIE, value=mode, max_age=3600, httponly=True)
    return response


@router.post("/new")
def assistant_new(request: Request, mode: str = Form("assistant"), db: Session = Depends(get_db)):
    """Clear the current session's chat history and remove uploaded files."""
    user = require_user(request, db)
    if mode not in _MODES:
        mode = (_resolve_mode(request) if mode not in _MODES else mode)
    cookie_name = _SESSION_COOKIES[mode]
    session_id = request.cookies.get(cookie_name)
    if session_id and _session_key(mode, session_id) in sessions:
        sessions[_session_key(mode, session_id)] = {"messages": [], "flags": {}}
        _cleanup_uploads(session_id)

    response = RedirectResponse(url=f"/assistant?mode={mode}", status_code=303)
    response.set_cookie(key=cookie_name, value=session_id or str(uuid.uuid4()), max_age=3600, httponly=True)
    response.set_cookie(key=_MODE_COOKIE, value=mode, max_age=3600, httponly=True)
    return response
