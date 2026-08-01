"""Service status router — live checks for Gitea, Elasticsearch, and the LLM.

Summary:
    Provides a /status page (linked from the profile menu) showing a green
    tick or red cross for each of the app's key dependencies:
      - Gitea (Git CAD file storage)
      - Elasticsearch (search backend)
      - LLM (the CHAT_MODEL from .env)

    The page is server-rendered from a rendered snapshot; /status/api returns
    the same data as JSON for programmatic use.
"""

import logging

import requests
import urllib3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import GITEA_BASE_URL, GITEA_USERNAME, GITEA_PASSWORD
from app.aisearch.config import (
    ES_HOST, ES_USER, ES_PASSWORD,
    LLM_BASE_URL, LLM_API_KEY, CHAT_MODEL,
)
from app.routers.auth import require_user, auth_context
from app.template_utils import render

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

router = APIRouter(prefix="/status", tags=["status"])

# The Gitea / Elasticsearch instances are local (self-signed / http), so
# requesting is best-effort and never blocks on TLS validation.
_TIMEOUT = 5


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


def _check_llm() -> dict:
    """Return whether the CHAT_MODEL from .env responds to a chat request.

    Sends the smallest possible request (1 token) so the check is cheap and
    fast. A 200 means the model works. 401/403 means the server is reachable
    but the API key is rejected; anything else is reported as an error.
    """
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": CHAT_MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            return {
                "service": "LLM (CHAT_MODEL)",
                "subtitle": CHAT_MODEL,
                "live": True,
                "message": "Model responded",
            }
        if resp.status_code in (401, 403):
            return {
                "service": "LLM (CHAT_MODEL)",
                "subtitle": CHAT_MODEL,
                "live": False,
                "message": f"API key rejected (HTTP {resp.status_code})",
            }
        return {
            "service": "LLM (CHAT_MODEL)",
            "subtitle": CHAT_MODEL,
            "live": False,
            "message": f"HTTP {resp.status_code}: {resp.text[:120]}",
        }
    except requests.RequestException as e:
        return {
            "service": "LLM (CHAT_MODEL)",
            "subtitle": CHAT_MODEL,
            "live": False,
            "message": f"Connection failed: {e.__class__.__name__}",
        }


def status_checks() -> list[dict]:
    """Run all dependency checks and return the results as a list."""
    return [_check_gitea(), _check_elasticsearch(), _check_llm()]


@router.get("/api", response_class=JSONResponse)
def status_api(request: Request, db: Session = Depends(get_db)):
    """JSON endpoint returning the live state of each dependency."""
    require_user(request, db)
    return JSONResponse(content={"checks": status_checks()})


@router.get("", response_class=HTMLResponse)
def status_page(request: Request, db: Session = Depends(get_db)):
    """Server-rendered status page with green ticks / red crosses."""
    require_user(request, db)
    ctx = auth_context(request, db)
    checks = status_checks()
    return HTMLResponse(content=render(
        "status.html",
        **ctx,
        checks=checks,
    ))
