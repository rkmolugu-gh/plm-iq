"""Service status router — live checks for Gitea, Elasticsearch, and all LLM models.

Summary:
    Provides a /status page (linked from the profile menu) showing a green
    tick or red cross for each of the app's key dependencies:
      - Gitea (Git CAD file storage)
      - Elasticsearch (search backend)
      - All LLM models from .env:
          * CHAT_MODEL (RAG chat)
          * EMBEDDING_MODEL (vector embeddings)
          * RERANKER_MODEL (reranking)
          * ASSISTANT_MODEL (PLM assistant with tools)
          * VISION_MODEL (image + text)

    The page is server-rendered from a rendered snapshot; /status/api returns
    the same data as JSON for programmatic use.
"""

import logging

import requests
import urllib3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import TenantScopedSession
from app.config import GITEA_BASE_URL, GITEA_USERNAME, GITEA_PASSWORD
from app.aisearch.config import (
    ES_HOST, ES_USER, ES_PASSWORD,
    LLM_BASE_URL, LLM_API_KEY, CHAT_MODEL,
    EMBEDDING_MODEL, RERANKER_MODEL, VISION_MODEL,
)
from app.plmassistant.config import ASSISTANT_MODEL
from app.routers.auth import require_user, auth_context, get_tenant_db
from app.template_utils import render

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(prefix="/status", tags=["status"])

# The Gitea / Elasticsearch instances are local (self-signed / http), so
# requesting is best-effort and never blocks on TLS validation.
_TIMEOUT = 5
_LLM_TIMEOUT = 15  # LLM checks need more time


def _check_gitea() -> dict:
    """Return the live state of the Gitea server.

    Any HTTP response (< 500) means the server answered — even a 401 means the
    instance is up and merely guarding its API. Only a transport-level failure
    (connection refused, DNS, TLS) counts as down.
    """
    url = f"{GITEA_BASE_URL}/api/v1/version"
    try:
        resp = requests.get(
            url, auth=(GITEA_USERNAME, GITEA_PASSWORD),
            timeout=_TIMEOUT, verify=False,
        )
        live = resp.status_code < 500
        return {
            "service": "Gitea",
            "subtitle": GITEA_BASE_URL,
            "live": live,
            "message": f"HTTP {resp.status_code}" if live
            else f"Server error (HTTP {resp.status_code})",
        }
    except requests.RequestException as e:
        return {
            "service": "Gitea",
            "subtitle": GITEA_BASE_URL,
            "live": False,
            "message": f"Connection failed: {e.__class__.__name__}",
        }


def _check_elasticsearch() -> dict:
    """Return the live state of the Elasticsearch server."""
    url = ES_HOST.rstrip("/") + "/"
    auth = (ES_USER, ES_PASSWORD) if ES_USER else None
    try:
        resp = requests.get(url, auth=auth, timeout=_TIMEOUT, verify=False)
        live = resp.status_code < 500
        return {
            "service": "Elasticsearch",
            "subtitle": ES_HOST,
            "live": live,
            "message": f"HTTP {resp.status_code}" if live
            else f"Server error (HTTP {resp.status_code})",
        }
    except requests.RequestException as e:
        return {
            "service": "Elasticsearch",
            "subtitle": ES_HOST,
            "live": False,
            "message": f"Connection failed: {e.__class__.__name__}",
        }


def _probe_chat_model(model_name: str, service_name: str) -> dict:
    """Check if a chat-completion model is accessible.

    Sends the smallest possible request (1 token) so the check is cheap and
    fast. A 200 means the model works. 401/403 means the server is reachable
    but the API key is rejected; anything else is reported as an error.
    """
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=_LLM_TIMEOUT)
        if resp.status_code == 200:
            return {
                "service": service_name,
                "subtitle": model_name,
                "live": True,
                "message": "Model responded",
            }
        if resp.status_code in (401, 403):
            return {
                "service": service_name,
                "subtitle": model_name,
                "live": False,
                "message": f"API key rejected (HTTP {resp.status_code})",
            }
        return {
            "service": service_name,
            "subtitle": model_name,
            "live": False,
            "message": f"HTTP {resp.status_code}: {resp.text[:120]}",
        }
    except requests.RequestException as e:
        return {
            "service": service_name,
            "subtitle": model_name,
            "live": False,
            "message": f"Connection failed: {e.__class__.__name__}",
        }


def _probe_embedding_model(model_name: str, service_name: str) -> dict:
    """Check if an embedding model is accessible.

    Sends a minimal embedding request (short text) to verify the model works.
    """
    url = f"{LLM_BASE_URL.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "input": "test",
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=_LLM_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and len(data["data"]) > 0:
                return {
                    "service": service_name,
                    "subtitle": model_name,
                    "live": True,
                    "message": f"Model responded ({len(data['data'][0].get('embedding', []))} dims)",
                }
        if resp.status_code in (401, 403):
            return {
                "service": service_name,
                "subtitle": model_name,
                "live": False,
                "message": f"API key rejected (HTTP {resp.status_code})",
            }
        return {
            "service": service_name,
            "subtitle": model_name,
            "live": False,
            "message": f"HTTP {resp.status_code}: {resp.text[:120]}",
        }
    except requests.RequestException as e:
        return {
            "service": service_name,
            "subtitle": model_name,
            "live": False,
            "message": f"Connection failed: {e.__class__.__name__}",
        }


def _check_chat_model() -> dict:
    """Check if CHAT_MODEL is accessible (used by aisearch RAG)."""
    return _probe_chat_model(CHAT_MODEL, "LLM (CHAT_MODEL)")


def _check_embedding_model() -> dict:
    """Check if EMBEDDING_MODEL is accessible (used for vector embeddings)."""
    return _probe_embedding_model(EMBEDDING_MODEL, "LLM (EMBEDDING_MODEL)")


def _check_reranker_model() -> dict:
    """Check if RERANKER_MODEL is accessible (used for reranking search results)."""
    return _probe_embedding_model(RERANKER_MODEL, "LLM (RERANKER_MODEL)")


def _check_assistant_model() -> dict:
    """Check if ASSISTANT_MODEL is accessible (used by PLM Assistant with tools)."""
    return _probe_chat_model(ASSISTANT_MODEL, "LLM (ASSISTANT_MODEL)")


def _check_vision_model() -> dict:
    """Check if VISION_MODEL is accessible (used for image + text)."""
    return _probe_chat_model(VISION_MODEL, "LLM (VISION_MODEL)")


def status_checks() -> list[dict]:
    """Run all dependency checks and return the results as a list."""
    return [
        _check_gitea(),
        _check_elasticsearch(),
        _check_chat_model(),
        _check_embedding_model(),
        _check_reranker_model(),
        _check_assistant_model(),
        _check_vision_model(),
    ]


@router.get("/api", response_class=JSONResponse)
def status_api(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """JSON endpoint returning the live state of each dependency."""
    require_user(request, db)
    return JSONResponse(content={"checks": status_checks()})


@router.get("", response_class=HTMLResponse)
def status_page(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Server-rendered status page with green ticks / red crosses."""
    require_user(request, db)
    ctx = auth_context(request, db)
    checks = status_checks()
    return HTMLResponse(content=render(
        "status.html",
        **ctx,
        checks=checks,
    ))
