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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# ── In-memory session store ──────────────────────────────────────
sessions: dict[str, dict] = {}

# ── Upload config ────────────────────────────────────────────────
_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


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


def _get_or_create_session(session_id: Optional[str]) -> tuple[str, dict]:
    """Return (session_id, session_data) — creates a new session if needed."""
    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = {"messages": [], "flags": {}}
    return session_id, sessions[session_id]


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
    """Render the assistant chat page with session history."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    session_id, session_data = _get_or_create_session(request.cookies.get("assistant_session"))
    messages = session_data["messages"]

    response = HTMLResponse(content=render(
        "assistant.html",
        messages=messages,
        **ctx,
        assistant_model=ASSISTANT_MODEL,
    ))
    response.set_cookie(key="assistant_session", value=session_id, max_age=3600, httponly=True)
    return response


@router.post("", response_class=HTMLResponse)
async def assistant_send(
    request: Request,
    message: str = Form("", description="User's message"),
    files: list[UploadFile] = File(default=[], description="Optional file attachments"),
    db: Session = Depends(get_db),
):
    """Process a user message through the PLM Assistant agent.

    Supports file attachments (images, PDFs, text). Images trigger the
    vision-aware LLM path; text-only queries use the tool-calling ReAct loop.
    """
    user = require_user(request, db)
    tenant_key = get_tenant_key(request, db)
    session_id, session_data = _get_or_create_session(request.cookies.get("assistant_session"))
    msgs = session_data["messages"]

    # 1. Process uploaded files
    uploaded_file_metas = []
    for f in files:
        if f.filename:
            meta = _process_uploaded_file(f, session_id)
            uploaded_file_metas.append(meta)

    # 2. Build user message content (multimodal if images present)
    user_content = prepare_assistant_messages(message, uploaded_file_metas)
    user_msg: dict = {"role": "user", "content": user_content}
    if uploaded_file_metas:
        user_msg["files"] = uploaded_file_metas
    if isinstance(user_content, list):
        display_text = message or " ".join(f"[{f['filename']}]" for f in uploaded_file_metas)
        user_msg["display_text"] = display_text
    msgs.append(user_msg)

    # 3. Build message list for the agent
    agent_messages = list(msgs)

    # 4. Call the agent
    logger.info(f"[assistant] Processing: session={session_id[:8]} msg='{message[:80]}' files={len(uploaded_file_metas)}")
    try:
        reply = assistant_chat(messages=agent_messages, tenant_key=tenant_key)
    except Exception as e:
        logger.exception(f"[assistant] Agent call failed: {e}")
        # Extract a user-friendly error message
        error_msg = str(e)
        # Remove any "RuntimeError: " prefix for cleaner display
        if error_msg.startswith("RuntimeError: "):
            error_msg = error_msg[len("RuntimeError: "):]
        reply = f"I'm sorry, I couldn't process that request. Error: {error_msg}"

    # 5. Store assistant reply
    assistant_msg: dict = {"role": "assistant", "content": reply}
    msgs.append(assistant_msg)

    # 6. Trim and evict
    _trim_history(session_data)
    _evict_if_needed()

    # 7. Redirect to GET (POST-Redirect-GET pattern)
    response = RedirectResponse(url="/assistant", status_code=303)
    response.set_cookie(key="assistant_session", value=session_id, max_age=3600, httponly=True)
    return response


@router.post("/new")
def assistant_new(request: Request, db: Session = Depends(get_db)):
    """Clear the current session's chat history and remove uploaded files."""
    user = require_user(request, db)
    session_id = request.cookies.get("assistant_session")
    if session_id and session_id in sessions:
        sessions[session_id] = {"messages": [], "flags": {}}
        _cleanup_uploads(session_id)

    response = RedirectResponse(url="/assistant", status_code=303)
    response.set_cookie(key="assistant_session", value=session_id or str(uuid.uuid4()), max_age=3600, httponly=True)
    return response
