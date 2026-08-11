"""CAD Metadata router."""

import asyncio
import base64
import io
import json
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse

from app.database import TenantScopedSession
from app.models import CadMetadata, User
from app.config import (
    DEFAULT_PAGE_SIZE,
    VOLUME_DIR,
    GITEA_BASE_URL,
    GITEA_OWNER,
    GITEA_REPO,
    GITEA_USERNAME,
    GITEA_PASSWORD,
    GITEA_BRANCH,
    GITEA_COMMIT_EMAIL,
)
from app.routers.auth import require_user, require_role, auth_context, get_tenant_db
from app.template_utils import render

logger = logging.getLogger(__name__)

# ── Debug helpers ─────────────────────────────────────────────

def _log_request_dump(part_number: str, filename: str, ref_type: str, file_size: int | None, step: str):
    """Emit a structured debug log line for the upload pipeline."""
    logger.debug(
        "UPLOAD [%s] part=%s file=%s ref_type=%s size=%s",
        step, part_number, filename, ref_type,
        f"{file_size} B" if file_size else "unknown",
    )

router = APIRouter(prefix="/cad")

# ── File upload helpers ────────────────────────────────────

# LocalServer keeps the original PDF-only restriction.
ALLOWED_UPLOAD_EXTENSIONS = {".pdf"}
# Git accepts real CAD formats (and PDF) so models can live in Gitea.
GIT_ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf", ".step", ".stp", ".dwg", ".dxf", ".sldprt", ".sldasm",
    ".stl", ".3mf", ".iges", ".igs", ".catpart", ".catproduct",
    ".x_t", ".x_b", ".prt", ".asm",
}
_REF_TYPES = ["LocalServer", "AWS S3", "Git"]


def _is_allowed_file(filename: str, ref_type: str = "LocalServer") -> bool:
    """Check if the file extension is allowed for the given reference type."""
    ext = Path(filename).suffix.lower()
    if ref_type == "Git":
        return ext in GIT_ALLOWED_UPLOAD_EXTENSIONS
    return ext in ALLOWED_UPLOAD_EXTENSIONS


def _gitea_cfg(request: Request):
    """Resolve the caller's tenant-scoped Gitea config (falls back to legacy)."""
    from app.git.tenant_gitea import resolve_config
    tenant_key = getattr(request.state, "tenant_key", None)
    return resolve_config(tenant_key)


def _gitea_raw_url(repo_path: str, cfg=None) -> str:
    """Build the raw-file download URL for a path in the tenant's CAD repo."""
    from app.git.tenant_gitea import resolve_config
    cfg = cfg or resolve_config(None)
    return cfg.raw_url(cfg.repo_cad, cfg.branch, repo_path)


def _gitea_put_file(content: bytes, repo_path: str, cfg=None):
    """Upload a single file to the tenant's CAD repo via the contents API.

    Delegates to the centralized per-tenant Gitea client (upsert semantics).
    Returns (raw_download_url, commit_sha, size_bytes), authenticating as the
    tenant so it can only write its own repo.

    Note: Gitea forbids advancing an existing branch ref, so a folder cannot be
    committed atomically — each file becomes its own commit.
    """
    from app.git.tenant_gitea import resolve_config, put_file
    cfg = cfg or resolve_config(None)
    return put_file(cfg, cfg.repo_cad, repo_path, content)


def _upload_gitea_folder(entries, username: str, part_number: str, cfg=None) -> dict:
    """Upload a list of (rel_path, content_bytes) files as an assembly under
    {username}/{part_number}/files/ in the tenant's CAD repo, preserving nested
    relative paths.

    Authenticates as the tenant (via ``cfg``), so files land only in that
    tenant's private repo. Returns a dict with folder_path, the last commit sha,
    the primary file's raw URL, a manifest list, and total size.
    """
    from app.git.tenant_gitea import resolve_config
    cfg = cfg or resolve_config(None)
    folder_path = f"{username}/{part_number}/files"
    manifest = []
    last_commit = None
    total_size = 0
    for rel_path, content in entries:
        repo_path = f"{folder_path}/{rel_path}"
        raw_url, commit_sha, size = _gitea_put_file(content, repo_path, cfg)
        manifest.append({
            "path": rel_path,
            "name": Path(rel_path).name,
            "size": size,
            "sha": commit_sha,
            "raw_url": raw_url,
        })
        last_commit = commit_sha
        total_size += size
    return {
        "folder_path": folder_path,
        "commit_sha": last_commit,
        "primary_raw_url": manifest[0]["raw_url"] if manifest else None,
        "manifest": manifest,
        "total_size": total_size,
    }


def _store_file_locally(file: UploadFile, part_number: str) -> tuple[str, int]:
    """Store an uploaded file under data/volume/{part_number}/ and return (relative_path, bytes)."""
    part_dir = Path(VOLUME_DIR) / part_number
    part_dir.mkdir(parents=True, exist_ok=True)

    dest_path = part_dir / file.filename
    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = dest_path.stat().st_size
    logger.info(f"Stored uploaded file: {dest_path} ({file_size} bytes)")
    return str(dest_path), file_size


# ── Routes ─────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def list_cad(
    request: Request,
    q: Optional[str] = Query(None, description="Search"),
    file_format: Optional[str] = Query(None, description="Filter by format"),
    page: int = Query(1, ge=1),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """List CAD metadata entries."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    query = db.query(CadMetadata)

    if q:
        query = query.filter(
            or_(
                CadMetadata.part_number.ilike(f"%{q}%"),
                CadMetadata.cad_file_name.ilike(f"%{q}%"),
                CadMetadata.cad_system.ilike(f"%{q}%"),
            )
        )
    if file_format:
        query = query.filter(CadMetadata.cad_file_format == file_format)

    total = query.count()
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    items = query.order_by(CadMetadata.part_number).offset(offset).limit(DEFAULT_PAGE_SIZE).all()

    return HTMLResponse(content=render(
        "cad/list.html",
        **ctx,
        items=items,
        page=page,
        total=total,
        pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        q=q or "",
        format_filter=file_format or "",
        formats=["SLDASM", "SLDPRT", "STEP", "STP", "DWG", "DXF", "STL", "3MF", "PDF"],
        ref_types=_REF_TYPES,
    ))


@router.get("/new", response_class=HTMLResponse)
def cad_new_form(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show CAD metadata creation form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "cad/new.html", **ctx,
        formats=["SLDASM", "SLDPRT", "STEP", "STP", "DWG", "DXF", "STL", "3MF", "PDF"],
        ref_types=_REF_TYPES,
    ))


@router.get("/{item_id}", response_class=HTMLResponse)
def cad_detail(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    """Show CAD metadata detail."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(CadMetadata).filter(CadMetadata.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    manifest = []
    try:
        if item.git_manifest:
            manifest = json.loads(item.git_manifest)
    except Exception:
        manifest = []
    is_assembly = item.file_reference_type == "Git" and len(manifest) > 1
    return HTMLResponse(content=render(
        "cad/detail.html", **ctx, item=item, manifest=manifest, is_assembly=is_assembly
    ))


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def cad_edit_form(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show CAD edit form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(CadMetadata).filter(CadMetadata.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render("cad/edit.html", **ctx, item=item))


@router.post("/{item_id}/edit", response_class=HTMLResponse)
def cad_edit_submit(
    request: Request,
    item_id: int,
    cad_file_name: str = Form(...),
    cad_file_format: str = Form(...),
    cad_system: str = Form(""),
    file_reference_type: str = Form("LocalServer"),
    file_size_bytes: int = Form(0),
    drawing_number: str = Form(""),
    model_type: str = Form(""),
    notes: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Update CAD metadata."""
    user = require_user(request, db)
    item = db.query(CadMetadata).filter(CadMetadata.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    item.cad_file_name = cad_file_name
    item.cad_file_format = cad_file_format
    item.cad_system = cad_system or None
    item.file_reference_type = file_reference_type or "LocalServer"
    item.file_size_bytes = file_size_bytes or None
    item.drawing_number = drawing_number or None
    item.model_type = model_type or None
    item.notes = notes or None
    db.commit()
    return RedirectResponse(url=f"/cad/{item_id}", status_code=303)


@router.post("/new", response_class=HTMLResponse)
def cad_new_submit(
    request: Request,
    part_number: str = Form(...),
    cad_file_name: str = Form(...),
    cad_file_format: str = Form(...),
    cad_system: str = Form(""),
    file_reference_type: str = Form("LocalServer"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Create new CAD metadata entry."""
    user = require_user(request, db)
    item = CadMetadata(
        part_number=part_number,
        cad_file_name=cad_file_name,
        cad_file_format=cad_file_format,
        cad_system=cad_system or None,
        file_reference_type=file_reference_type or "LocalServer",
        tenant_id=1,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/cad/{item.id}", status_code=303)


@router.post("/upload", response_class=HTMLResponse)
async def cad_upload(
    request: Request,
    part_number: str = Form(...),
    files: list[UploadFile] = File(...),
    file_reference_type: str = Form("LocalServer"),
    is_folder: bool = Form(False),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Upload a CAD file or an entire folder (assembly) and create one
    CadMetadata record.

    For LocalServer, a single PDF is stored under data/volume/{part_number}/.
    For Git, files are pushed to the Gitea repo at
    {username}/{part_number}/files/{relative_path}. A folder upload preserves
    its nested structure and is recorded as a single "ASSEMBLY" record with a
    manifest of all contained files.
    """
    display = ", ".join(f.filename or "?" for f in files)[:200]
    _log_request_dump(part_number, display, file_reference_type, None, "ENTER")

    def _error_page(msg: str, status: int = 400) -> HTMLResponse:
        logger.warning("UPLOAD [FAIL] %s — part=%s files=%s", msg, part_number, display)
        return HTMLResponse(
            content=render("404.html", message=msg),
            status_code=status,
        )

    if not files:
        return _error_page("no file(s) provided")

    # Relative paths: a folder selection (webkitdirectory) yields paths like
    # "AssemblyX/drawings/a.step"; strip the top folder so the assembly's
    # internal structure lives directly under files/. Single-file uploads keep
    # just the base name.
    def _relative_path(filename: str) -> str:
        parts = filename.replace("\\", "/").split("/")
        return "/".join(parts[1:]) if (has_dir and len(parts) > 1) else parts[-1]

    has_dir = is_folder or any("/" in (f.filename or "").replace("\\", "/") for f in files)

    # Validate extensions per reference type - now all ref types support all formats
    for f in files:
        if not f.filename:
            return _error_page("a file with no name was provided")
        if not _is_allowed_file(f.filename, file_reference_type):
            ext = Path(f.filename).suffix.lower()
            if file_reference_type == "Git":
                return _error_page(
                    f"disallowed extension '{ext}' for Git — allowed: "
                    f"{', '.join(sorted(e.lstrip('.') for e in GIT_ALLOWED_UPLOAD_EXTENSIONS))}"
                )
            elif file_reference_type == "LocalServer":
                return _error_page(f"disallowed extension '{ext}' — allowed: "
                    f"{', '.join(sorted(e.lstrip('.') for e in ALLOWED_UPLOAD_EXTENSIONS))}")
            return _error_page(f"disallowed extension '{ext}'")

    logger.debug("UPLOAD [OK] validation passed for %d file(s)", len(files))

    file_size = 0
    file_reference_url = None
    git_repo_path = None
    git_commit_sha = None
    git_manifest = None
    cad_file_format = "PDF"
    cad_file_name = files[0].filename
    current_user = require_user(request, db)
    username = current_user.username or "unknown"

    if file_reference_type == "LocalServer":
        logger.debug("UPLOAD [STORE] ref_type=LocalServer → storing %d file(s) locally", len(files))
        _log_request_dump(part_number, display, file_reference_type, file_size, "STORE_BEGIN")
        try:
            stored_files = []
            total_size = 0
            for f in files:
                if hasattr(f.file, "seekable") and f.file.seekable():
                    f.file.seek(0, os.SEEK_END)
                    f.file.seek(0)
                ref_url, size = _store_file_locally(f, part_number)
                stored_files.append((f.filename, ref_url, size))
                total_size += size
            file_reference_url = stored_files[0][1] if stored_files else None
            file_size = total_size
            if len(files) > 1:
                cad_file_format = "ASSEMBLY"
                if has_dir:
                    cad_file_name = files[0].filename.replace("\\", "/").split("/")[0]
            else:
                cad_file_format = Path(files[0].filename).suffix.lstrip(".").upper() or "PDF"
        except Exception as e:
            logger.exception("UPLOAD [STORE_FAIL] could not write file: %s", e)
            return _error_page(f"Failed to store file: {e}", status=500)
        _log_request_dump(part_number, display, file_reference_type, file_size, "STORE_DONE")
        logger.info("UPLOAD [STORE] wrote %d bytes (%d file(s)) to %s", file_size, len(files), file_reference_url)

    elif file_reference_type == "Git":
        logger.debug("UPLOAD [GITEA] ref_type=Git → pushing %d file(s) to Gitea repo", len(files))
        _log_request_dump(part_number, display, file_reference_type, file_size, "GITEA_BEGIN")
        try:
            entries = [( _relative_path(f.filename), await f.read()) for f in files]
            cfg = _gitea_cfg(request)
            result = await asyncio.to_thread(
                _upload_gitea_folder, entries, username, part_number, cfg
            )
            git_repo_path = result["folder_path"]
            git_commit_sha = result["commit_sha"]
            file_reference_url = result["primary_raw_url"]
            git_manifest = json.dumps(result["manifest"])
            file_size = result["total_size"]
            is_assembly = len(files) > 1
            cad_file_format = "ASSEMBLY" if is_assembly else (
                Path(_relative_path(files[0].filename)).suffix.lstrip(".").upper() or "PDF"
            )
            if has_dir:
                cad_file_name = files[0].filename.replace("\\", "/").split("/")[0]
        except Exception as e:
            logger.exception("UPLOAD [GITEA_FAIL] could not push to Gitea: %s", e)
            detail = getattr(getattr(e, "response", None), "text", str(e))
            return _error_page(f"Gitea upload failed: {detail}", status=502)
        _log_request_dump(part_number, display, file_reference_type, file_size, "GITEA_DONE")
        logger.info(
            "UPLOAD [GITEA] pushed %d bytes (%d file(s)) to %s (last commit %s)",
            file_size, len(files), git_repo_path, git_commit_sha,
        )
    else:
        # AWS S3 or others — store the reference only, file handling is external
        logger.debug("UPLOAD [SKIP] ref_type=%s — recording reference only", file_reference_type)
        if len(files) > 1:
            cad_file_format = "ASSEMBLY"
            if has_dir:
                cad_file_name = files[0].filename.replace("\\", "/").split("/")[0]
            # For multiple files, create a reference that includes all filenames
            file_reference_url = f"{file_reference_type.lower()}://{part_number}/" + ",".join(f.filename for f in files)
        else:
            file_reference_url = f"{file_reference_type.lower()}://{part_number}/{files[0].filename}"
            cad_file_format = Path(files[0].filename).suffix.lstrip(".").upper() or "PDF"

    # Create the CAD metadata record
    logger.debug("UPLOAD [DB] creating CadMetadata record")
    try:
        item = CadMetadata(
            part_number=part_number,
            cad_file_name=cad_file_name,
            cad_file_format=cad_file_format,
            cad_system="",
            file_reference_type=file_reference_type,
            file_reference_url=file_reference_url,
            git_repo_path=git_repo_path,
            git_commit_sha=git_commit_sha,
            git_manifest=git_manifest,
            file_size_bytes=file_size or None,
            tenant_id=1,
        )
        db.add(item)
        db.flush()
        item_id = item.id
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("UPLOAD [DB_FAIL] could not create record: %s", e)
        return _error_page(f"Database error: {e}", status=500)

    _log_request_dump(part_number, display, file_reference_type, file_size, "COMMIT_DONE")
    logger.info(
        "UPLOAD [DONE] id=%s part=%s files=%d size=%s ref_type=%s format=%s",
        item_id, part_number, len(files),
        f"{file_size} B" if file_size else "?",
        file_reference_type, cad_file_format,
    )

    return RedirectResponse(url=f"/cad/{item_id}", status_code=303)


@router.get("/{item_id}/view")
def cad_view(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    """Render a PDF inline in the browser for a CAD record.

    Only works for LocalServer ref type — the file must exist on disk.
    """
    from fastapi.responses import FileResponse, Response

    require_user(request, db)
    item = db.query(CadMetadata).filter(CadMetadata.id == item_id).first()
    if not item:
        logger.warning("VIEW [404] CAD record id=%s not found", item_id)
        return HTMLResponse(content=render("404.html"), status_code=404)

    logger.debug("VIEW [LOOKUP] id=%s part=%s file=%s ref_type=%s path=%s",
                 item_id, item.part_number, item.cad_file_name,
                 item.file_reference_type, item.file_reference_url)

    if item.file_reference_type != "LocalServer" or not item.file_reference_url:
        logger.warning("VIEW [UNAVAIL] ref_type=%s url=%s — not a LocalServer file",
                       item.file_reference_type, item.file_reference_url)
        return Response(
            content=render("404.html"),
            status_code=404,
        )

    file_path = Path(item.file_reference_url)
    if not file_path.exists():
        logger.warning("VIEW [NOT_FOUND] file not on disk: %s", file_path)
        return Response(
            content=render("404.html"),
            status_code=404,
        )

    logger.info("VIEW [OK] serving inline: %s (%d bytes)", file_path, file_path.stat().st_size)
    return FileResponse(
        path=str(file_path),
        filename=item.cad_file_name,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/{item_id}/download")
def cad_download(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    """Download the uploaded file for a CAD record.

    For LocalServer, the file is served from disk. For Git, the user is
    redirected to the raw file URL in the Gitea repo.
    """
    from fastapi.responses import FileResponse

    require_user(request, db)
    item = db.query(CadMetadata).filter(CadMetadata.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html"), status_code=404)

    if item.file_reference_type == "Git":
        from app.downloads.proxy import file_response
        from app.downloads.zips import zip_cache_key, zip_response
        cfg = _gitea_cfg(request)
        manifest = []
        try:
            if item.git_manifest:
                manifest = json.loads(item.git_manifest)
        except Exception:
            manifest = []

        # An assembly (multiple files) is delivered as a single zip. It is built
        # once, cached to disk, and served with HTTP Range so the browser can
        # pause and resume the download.
        if len(manifest) > 1:
            logger.info("DOWNLOAD [GITEA_ZIP] id=%s → zipping %d files", item_id, len(manifest))
            entries = []
            key_entries = []
            for entry in manifest:
                repo_path = f"{item.git_repo_path}/{entry['path']}"
                arc = entry["path"]
                entries.append((repo_path, arc))
                key_entries.append((repo_path, arc, entry.get("sha") or ""))
            tenant_key = getattr(request.state, "tenant_key", None) or ""
            cache_key = zip_cache_key(tenant_key, "cad", item.id, item.git_repo_path or "", key_entries)
            return zip_response(cfg, cfg.repo_cad, cache_key, entries,
                                filename=f"{item.part_number}_cad.zip")

        if not item.git_repo_path:
            return HTMLResponse(
                content=render("404.html", error="No Gitea path recorded."),
                status_code=404,
            )
        # Single file → resumable (Range-aware) proxy of the private repo blob.
        return file_response(
            request, cfg, cfg.repo_cad, item.git_repo_path,
            total=item.file_size or 0,
            etag=item.git_commit_sha or "",
            filename=item.cad_file_name or "download",
        )

    if item.file_reference_type != "LocalServer" or not item.file_reference_url:
        return HTMLResponse(
            content=render("404.html", error="File not available for download."),
            status_code=404,
        )

    file_path = Path(item.file_reference_url)
    if not file_path.exists():
        logger.warning(f"Download requested but file not found: {file_path}")
        return HTMLResponse(
            content=render("404.html", error="File not found on disk."),
            status_code=404,
        )

    return FileResponse(
        path=str(file_path),
        filename=item.cad_file_name,
        media_type="application/pdf",
    )


@router.post("/{item_id}/delete", response_class=HTMLResponse)
def cad_delete(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Delete a CAD metadata record and its stored file (if LocalServer), then redirect."""
    user = require_user(request, db)
    item = db.query(CadMetadata).filter(CadMetadata.id == item_id).first()
    if item:
        if item.file_reference_type == "LocalServer" and item.file_reference_url:
            try:
                Path(item.file_reference_url).unlink(missing_ok=True)
            except OSError as e:
                logger.warning("DELETE [FILE_FAIL] could not remove %s: %s", item.file_reference_url, e)
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/cad", status_code=303)