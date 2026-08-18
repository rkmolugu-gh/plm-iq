"""APS Viewer router — a web-based CAD/3D model viewer powered by Autodesk
Platform Services.

The viewer loads a model that already lives on the server (configurable via
``APS_MODEL_DIR``). It is uploaded to an APS OSS bucket, translated to SVF2 by
Model Derivative, and rendered in the browser via the APS Viewer library.

Endpoints:
  GET  /apsviewer              -> viewer page (server-rendered)
  GET  /apsviewer/api/token    -> viewer access token (JSON)
  GET  /apsviewer/api/models   -> list of stored server models (JSON)
  POST /apsviewer/api/models/{filename}/upload+translate ->
         upload a server model file and kick off translation (JSON)
  GET  /apsviewer/api/models/{filename}/status -> translation status (JSON)
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.apsviewer.client import APSClient, APSError
from app.config import APS_MODEL_DIR
from app.database import TenantScopedSession
from app.routers.auth import auth_context, get_tenant_db, require_user
from app.template_utils import render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apsviewer", tags=["apsviewer"])


def _model_dir() -> Path:
    d = Path(APS_MODEL_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _client() -> APSClient:
    return APSClient()


def _server_models() -> list[dict]:
    """List the local model files on the server that the viewer can load."""
    d = _model_dir()
    found = []
    for path in sorted(d.iterdir()):
        if path.is_file():
            found.append({
                "filename": path.name,
                "size": path.stat().st_size,
            })
    return found


@router.get("", response_class=HTMLResponse)
def apsviewer_page(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Render the APS Viewer page."""
    require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render("apsviewer/viewer.html", **ctx, aps_model_dir=APS_MODEL_DIR))


@router.get("/api/token", response_class=JSONResponse)
def viewer_token(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Return a short-lived 2-legged token for the browser viewer."""
    require_user(request, db)
    try:
        return JSONResponse(content=_client().get_viewer_token())
    except APSError as e:
        return JSONResponse(
            content={"error": str(e), "aps_configured": bool(_client()._client_id)},
            status_code=502,
        )


@router.get("/api/models", response_class=JSONResponse)
def list_models(request: Request, db: TenantScopedSession = Depends(get_tenant_db)):
    """Return the list of server-side model files that can be viewed."""
    require_user(request, db)
    return JSONResponse(content={"models": _server_models()})


@router.post("/api/models/{filename}/translate", response_class=JSONResponse)
def translate_model(
    request: Request,
    filename: str,
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Upload a local server model file to APS and start an SVF2 translation."""
    require_user(request, db)
    file_path = _model_dir() / filename
    if not file_path.is_file():
        return JSONResponse(content={"error": f"Model file '{filename}' not found on the server (looked in {APS_MODEL_DIR})."},
                            status_code=404)

    client = _client()
    try:
        obj = client.upload_file(filename, str(file_path))
        object_id = obj.get("objectId") or obj.get("object_id")
        if not object_id:
            # Fall back to objectKey if the API returned only an objectKey.
            object_key = obj.get("objectKey") or filename
            object_id = f"urn:adsk.objects:os.object:{client._bucket}/{object_key}"
        # The Model Derivative API expects the objectId url-safe base64 encoded.
        urn = APSClient.urnify(object_id)

        root_filename = filename if filename.lower().endswith(".zip") else None

        result = client.translate_object(urn, root_filename=root_filename)
        return JSONResponse(
            content={
                "name": filename,
                "urn": urn,
                "translate_status": result,
                "message": "Translation job accepted. Poll /api/models/{filename}/status.",
            }
        )
    except (APSError, OSError) as e:
        logger.exception("APS translate failed for %s", filename)
        return JSONResponse(
            content={"error": f"Translation failed: {e}"},
            status_code=502,
        )


@router.get("/api/models/{filename}/status", response_class=JSONResponse)
def model_status(
    request: Request,
    filename: str,
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """Return the translation status for a stored model file."""
    require_user(request, db)
    file_path = _model_dir() / filename
    if not file_path.is_file():
        return JSONResponse(content={"error": f"Model file '{filename}' not found on the server."}, status_code=404)

    try:
        objects = _client().list_objects()
        match = next((o for o in objects if o.get("objectKey") == filename), None)
        if not match:
            return JSONResponse(content={"status": "n/a", "message": "Not uploaded to APS yet."})

        object_id = match.get("objectId") or f"urn:adsk.objects:os.object:{_client()._bucket}/{filename}"
        urn = APSClient.urnify(object_id)
        manifest = _client().get_manifest(urn)
        if manifest is None:
            # Uploaded but not translated.
            return JSONResponse(
                content={"status": "n/a", "urn": urn,
                         "message": "Uploaded. Model has not been translated — start translation."}
            )
        messages = _collect_messages(manifest)
        return JSONResponse(
            content={"status": manifest.get("status"), "progress": manifest.get("progress"),
                     "urn": urn, "messages": messages}
        )
    except APSError as e:
        logger.exception("APS status failed for %s", filename)
        return JSONResponse(content={"error": f"Status check failed: {e}"}, status_code=502)


def _collect_messages(manifest: dict) -> list:
    """Aggregate error/warning messages from a manifest into a flat list."""
    messages = []
    for derivative in manifest.get("derivatives") or []:
        messages.extend(derivative.get("messages") or [])
        for child in derivative.get("children") or []:
            messages.extend(child.get("messages") or [])
    return messages
