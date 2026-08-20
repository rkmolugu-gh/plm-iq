"""Standalone Document Management System router.

Documents live in a hidden Gitea repo (independent of users and parts), with a
self-referential hierarchy in the `documents` table. Folders are containers
(kind="folder"); files (kind="file") are pushed individually to Gitea at a path
derived from the hierarchy: {tenant_id}/<ancestor-folders>/<name>. Folders are
NOT zipped on upload — each contained file is committed on its own (Gitea 1.27's
refs API is blocked, so atomic multi-file commits are impossible). Downloading a
folder returns a structure-preserving zip.
"""

import asyncio
import base64
import datetime
import hashlib
import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.database import TenantScopedSession
from app.models import Document, User, Favorite, Part, GraphNode, GraphEdge, GraphEdgeType, GraphEdgeEvidence
from app.graph.service import document_linked_parts
from app.config import (
    DEFAULT_PAGE_SIZE,
    DOCUMENTS_GITEA_REPO,
    GITEA_BASE_URL,
    GITEA_OWNER,
    GITEA_USERNAME,
    GITEA_PASSWORD,
    GITEA_BRANCH,
    GITEA_COMMIT_EMAIL,
    DOC_ALLOWED_EXTENSIONS,
    VOLUME_DIR,
)
from app.routers.auth import require_user, require_role, auth_context, get_tenant_db, get_settings
from app.sequence import next_object_id
from app.template_utils import render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents")

_DOC_CATEGORIES = ["SPEC", "MANUAL", "CERT", "CONTRACT", "STANDARD", "DRAWING", "OTHER"]
from app.settings import DEFAULT_SETTINGS

# Domain list from centralised settings; used for validation in routes that
# don't have a Request. Dropdowns use get_settings(request).DOC_STATUSES.
_DOC_STATUSES = DEFAULT_SETTINGS["DOC_STATUSES"]


# ── Git helpers ──────────────────────────────────────────────

def _gitea_doc_cfg(request: Request):
    """Resolve the caller's tenant-scoped Gitea config (falls back to legacy)."""
    from app.git.tenant_gitea import resolve_config
    tenant_key = getattr(request.state, "tenant_key", None)
    return resolve_config(tenant_key)


def _gitea_doc_auth(cfg=None):
    from app.git.tenant_gitea import resolve_config
    cfg = cfg or resolve_config(None)
    return cfg.auth or (GITEA_USERNAME, GITEA_PASSWORD)


def _gitea_doc_raw_url(repo_path: str, cfg=None) -> str:
    """Raw-file download URL for a path in the tenant's documents repo."""
    from app.git.tenant_gitea import resolve_config
    cfg = cfg or resolve_config(None)
    return cfg.raw_url(cfg.repo_docs, cfg.branch, repo_path)


def _gitea_doc_ensure_repo(cfg=None):
    """Idempotently provision the tenant's private documents repo.

    With per-tenant isolation the repo is own by the tenant's Gitea user and is
    private (downloads are proxied through the app rather than served publicly).
    If given no config, resolves the legacy shared repo for single-tenant/dev.
    """
    from app.git.tenant_gitea import resolve_config
    cfg = cfg or resolve_config(None)
    url = f"{GITEA_BASE_URL}/api/v1/repos/{cfg.owner}/{cfg.repo_docs}"
    r = requests.get(url, auth=cfg.auth, timeout=30)
    if r.status_code == 200:
        return
    payload = {
        "name": cfg.repo_docs,
        "private": True,
        "auto_init": True,
        "default_branch": GITEA_BRANCH,
    }
    resp = requests.post(f"{GITEA_BASE_URL}/api/v1/user/repos",
                         auth=cfg.auth, json=payload, timeout=30)
    # 201 created, 409 already exists — both fine.
    if resp.status_code not in (200, 201, 409):
        logger.warning("DOCREPO [WARN] ensure repo returned %s: %s",
                       resp.status_code, resp.text[:300])


def _gitea_doc_put(content: bytes, repo_path: str, cfg=None):
    """Upload one file to the tenant's documents repo (upsert).

    Delegates to the centralized per-tenant Gitea client, authenticating as the
    tenant so it can only write its own repo. Returns
    (raw_download_url, commit_sha, size_bytes).
    """
    from app.git.tenant_gitea import resolve_config, put_file
    cfg = cfg or resolve_config(None)
    return put_file(cfg, cfg.repo_docs, repo_path, content)


def _gitea_doc_delete(repo_path: str, cfg=None):
    """Best-effort delete of a file in the tenant's documents repo."""
    from app.git.tenant_gitea import resolve_config, delete_file
    cfg = cfg or resolve_config(None)
    delete_file(cfg, cfg.repo_docs, repo_path)


def _store_document_locally(content: bytes, parent_id, file_name: str, tenant_id: int) -> str:
    """Store a document file under VOLUME_DIR/documents/ and return the stored path."""
    rel = Path(str(parent_id or "root")) / file_name
    dest = Path(VOLUME_DIR) / "documents" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return str(dest)


# ── Hierarchy helpers ───────────────────────────────────────

def _today() -> str:
    return datetime.date.today().isoformat()


def _bump_version(v: Optional[str]) -> str:
    """Bump a 'X.Y' version's minor component; leave unknown formats untouched."""
    m = re.match(r"^(\d+)\.(\d+)$", v or "")
    if m:
        return f"{int(m.group(1))}.{int(m.group(2)) + 1}"
    return v or "1.0"


def _path_from_root(db: Session, doc: Document) -> list:
    """Return [name, ...] from the root down to `doc` (inclusive)."""
    names = []
    cur = doc
    guard = 0
    while cur is not None and guard < 100:
        names.append(cur.name)
        if cur.parent_id is None:
            break
        cur = db.query(Document).filter(Document.id == cur.parent_id).first()
        guard += 1
    names.reverse()
    return names


def _compute_repo_path(db: Session, doc: Document) -> str:
    """Git path for a file doc: {tenant_id}/<folders>/<name>."""
    names = _path_from_root(db, doc)
    return f"{doc.tenant_id}/" + "/".join(names)


def _breadcrumb(db: Session, parent_id) -> list:
    """List of (id, name) from root to the given parent (exclusive of parent's own row context)."""
    crumbs = []
    cur_id = parent_id
    guard = 0
    while cur_id is not None and guard < 100:
        doc = db.query(Document).filter(Document.id == cur_id).first()
        if not doc:
            break
        crumbs.append((doc.id, doc.name))
        cur_id = doc.parent_id
        guard += 1
    crumbs.reverse()
    return crumbs


def _get_or_create_folder(db: Session, parent_id, name: str, tenant_id: int, user_id: int, tenant_key: str, storage_backend: str = "LocalServer") -> tuple:
    existing = (
        db.query(Document)
        .filter(
            Document.tenant_id == tenant_id,
            Document.parent_id == parent_id,
            Document.kind == "folder",
            Document.name == name,
        )
        .first()
    )
    if existing:
        return existing, False
    folder = Document(
        parent_id=parent_id,
        kind="folder",
        name=name,
        title=name,
        doc_category="OTHER",
        status="DRAFT",
        storage_backend=storage_backend,
        created_by=user_id,
        modified_by=user_id,
        created_date=_today(),
        modified_date=_today(),
        tenant_id=tenant_id,
        tenant_key=tenant_key,
    )
    db.add(folder)
    db.flush()
    return folder, True


def _upsert_file(db: Session, parent_id, name: str, tenant_id: int, user_id: int, tenant_key: str, storage_backend: str = "LocalServer") -> tuple:
    """Return (file_doc, is_new). Caller decides version bumping on revision."""
    existing = (
        db.query(Document)
        .filter(
            Document.tenant_id == tenant_id,
            Document.parent_id == parent_id,
            Document.kind == "file",
            Document.name == name,
        )
        .first()
    )
    if existing:
        existing.modified_by = user_id
        existing.modified_date = _today()
        return existing, False
    file_doc = Document(
        parent_id=parent_id,
        kind="file",
        name=name,
        title=name,
        doc_category="OTHER",
        status="DRAFT",
        doc_version="1.0",
        storage_backend=storage_backend,
        created_by=user_id,
        modified_by=user_id,
        created_date=_today(),
        modified_date=_today(),
        tenant_id=tenant_id,
        tenant_key=tenant_key,
    )
    db.add(file_doc)
    db.flush()
    # Only assign a human-friendly document number to newly created files.
    tkey = getattr(db, "tenant_key", None)
    file_doc.document_number = next_object_id(db, "doc", tkey)
    db.flush()
    return file_doc, True


def _collect_file_descendants(db: Session, doc: Document) -> list:
    """All file Documents beneath `doc` (recursive)."""
    result = []
    stack = [doc]
    guard = 0
    while stack and guard < 10000:
        cur = stack.pop()
        children = (
            db.query(Document)
            .filter(Document.parent_id == cur.id, Document.tenant_id == doc.tenant_id)
            .all()
        )
        for c in children:
            if c.kind == "file":
                result.append(c)
            else:
                stack.append(c)
        guard += 1
    return result


# ── Routes ──────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def list_documents(
    request: Request,
    parent_id: Optional[int] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    require_user(request, db)
    ctx = auth_context(request, db)
    tenant_id = ctx["current_user"].tenant_id

    total = (
        db.query(Document)
        .filter(Document.tenant_id == tenant_id, Document.parent_id == parent_id)
        .count()
    )
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    children = (
        db.query(Document)
        .filter(Document.tenant_id == tenant_id, Document.parent_id == parent_id)
        .order_by(Document.kind, Document.name)
        .offset(offset)
        .limit(DEFAULT_PAGE_SIZE)
        .all()
    )

    doc_ids = [c.id for c in children if c.kind == "file"]
    link_map = {}
    if doc_ids:
        doc_node_map = {
            d.node_id: d.id
            for d in db.query(Document.id, Document.node_id)
            .filter(Document.id.in_(doc_ids), Document.node_id.isnot(None))
            .all()
        }
        node_ids = list(doc_node_map.keys())
        edges = (
            db.query(GraphEdge)
            .filter(GraphEdge.target_node_id.in_(node_ids))
            .all()
        )
        part_node_ids = {e.source_node_id for e in edges}
        part_map = {}
        if part_node_ids:
            for row in db.query(Part).filter(Part.node_id.in_(part_node_ids)).all():
                part_map[row.node_id] = row
        # Edge types are a global, non-tenant vocabulary; read them unscoped so
        # the tenant-scoped session (which filters by the tenant's key) still
        # resolves names instead of falling back to the numeric edge_type_id.
        edge_type_map = {et.id: et.name for et in db._db.query(GraphEdgeType).all()}
        for e in edges:
            doc_id = doc_node_map.get(e.target_node_id)
            if doc_id is None:
                continue
            if doc_id not in link_map:
                link_map[doc_id] = []
            part = part_map.get(e.source_node_id)
            link_map[doc_id].append({
                "part_number": part.part_number if part else str(e.source_node_id),
                "part_revision": part.part_revision if part else "-",
                "edge_type": edge_type_map.get(e.edge_type_id, str(e.edge_type_id)),
            })

    return HTMLResponse(content=render(
        "documents/list.html",
        **ctx,
        parent_id=parent_id,
        breadcrumb=_breadcrumb(db, parent_id),
        children=children,
        link_map=link_map,
        q=q or "",
        page=page,
        total=total,
        pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        categories=_DOC_CATEGORIES,
        statuses=get_settings(request).DOC_STATUSES,
        parts=db.query(Part).order_by(Part.part_number, Part.part_revision).all(),
        document_edge_types=get_settings(request).DOCUMENT_EDGE_TYPES,
    ))


@router.post("/folder", response_class=HTMLResponse)
def create_folder(
    request: Request,
    name: str = Form(...),
    parent_id: Optional[str] = Form(None),
    doc_category: str = Form("OTHER"),
    status: str = Form("DRAFT"),
    description: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    tenant_id = user.tenant_id
    tenant_key = getattr(request.state, "tenant_key", None) or user.tenant_key
    name = (name or "").strip()
    parent_id = int(parent_id) if parent_id else None
    if not name:
        ctx = auth_context(request, db)
        return HTMLResponse(
            content=render("404.html", **ctx, error="Folder name is required."),
            status_code=400,
        )
    folder, _ = _get_or_create_folder(db, parent_id, name, tenant_id, user.user_id, tenant_key, "LocalServer")
    folder.doc_category = doc_category if doc_category in _DOC_CATEGORIES else "OTHER"
    folder.status = status if status in _DOC_STATUSES else "DRAFT"
    folder.description = description or None
    folder.modified_by = user.user_id
    folder.modified_date = _today()
    db.commit()
    return RedirectResponse(url=f"/documents?parent_id={parent_id or ''}", status_code=303)


@router.get("/{item_id}", response_class=HTMLResponse)
def document_detail(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)

    linked_part = None
    if item.node_id:
        links = document_linked_parts(db, item.node_id)
        if links:
            linked_part = links[0]

    child_list = []
    if item.kind == "folder":
        child_list = (
            db.query(Document)
            .filter(Document.parent_id == item.id, Document.tenant_id == item.tenant_id)
            .order_by(Document.kind, Document.name)
            .all()
        )
    return HTMLResponse(content=render(
        "documents/detail.html",
        **ctx,
        item=item,
        children=child_list,
        breadcrumb=_breadcrumb(db, item.parent_id),
        linked_part=linked_part,
    ))


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def document_edit_form(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)

    is_favorite = db.query(Favorite).filter(
        Favorite.user_id == user.user_id,
        Favorite.object_type == "document",
        Favorite.object_id == str(item_id),
    ).first() is not None

    linked_parts = []
    if item.node_id:
        edges = (
            db.query(GraphEdge, GraphEdgeType, Part)
            .join(GraphEdgeType, GraphEdge.edge_type_id == GraphEdgeType.id)
            .join(Part, Part.node_id == GraphEdge.source_node_id)
            .filter(GraphEdge.target_node_id == item.node_id)
            .all()
        )
        for edge, etype, part in edges:
            linked_parts.append({
                "node_id": part.node_id,
                "part_number": part.part_number,
                "edge_type": etype.name,
                "edge_id": edge.id,
            })

    return HTMLResponse(content=render(
        "documents/edit.html",
        **ctx,
        item=item,
        categories=_DOC_CATEGORIES,
        statuses=get_settings(request).DOC_STATUSES,
        is_favorite=is_favorite,
        linked_parts=linked_parts,
        parts=db.query(Part).order_by(Part.part_number, Part.part_revision).all(),
        document_edge_types=get_settings(request).DOCUMENT_EDGE_TYPES,
    ))


@router.post("/{item_id}/edit", response_class=HTMLResponse)
def document_edit_submit(
    request: Request,
    item_id: int,
    title: str = Form(""),
    doc_category: str = Form("OTHER"),
    doc_system: str = Form(""),
    status: str = Form("DRAFT"),
    description: str = Form(""),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    item.title = title or item.name
    item.doc_category = doc_category if doc_category in _DOC_CATEGORIES else "OTHER"
    item.doc_system = doc_system or None
    item.status = status if status in _DOC_STATUSES else "DRAFT"
    item.description = description or None
    item.modified_by = user.user_id
    item.modified_date = _today()
    db.commit()
    return RedirectResponse(url=f"/documents/{item.id}", status_code=303)


@router.post("/{item_id}/link", response_class=HTMLResponse)
def link_document_to_part(
    request: Request,
    item_id: int,
    part_id: str = Form(...),
    edge_type: str = Form("HAS_SPEC"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    part = db.query(Part).filter(Part.part_id == int(part_id)).first()
    if not part or not part.node_id:
        return RedirectResponse(url=f"/documents/{item_id}/edit", status_code=303)

    doc_node_id = item.node_id
    if not doc_node_id:
        node = GraphNode(
            node_label=item.title or item.name,
            created_by=item.created_by,
            created_date=_today(),
            tenant_id=item.tenant_id,
            tenant_key=item.tenant_key,
        )
        db.add(node)
        db.flush()
        item.node_id = node.node_id
        doc_node_id = node.node_id
        db.add(item)
        db.commit()

    etype = db.query(GraphEdgeType).filter(GraphEdgeType.name == edge_type).first()
    if not etype:
        return RedirectResponse(url=f"/documents/{item_id}/edit", status_code=303)

    exists = db.query(GraphEdge).filter(
        GraphEdge.source_node_id == part.node_id,
        GraphEdge.target_node_id == doc_node_id,
        GraphEdge.edge_type_id == etype.id,
        GraphEdge.tenant_key == item.tenant_key,
    ).first()
    if not exists:
        db.add(GraphEdge(
            source_node_id=part.node_id,
            target_node_id=doc_node_id,
            edge_type_id=etype.id,
            state="ACTIVE",
            created_date=_today(),
            updated_date=_today(),
            tenant_id=item.tenant_id,
            tenant_key=item.tenant_key,
        ))
        db.flush()
        edge = db.query(GraphEdge).filter(
            GraphEdge.source_node_id == part.node_id,
            GraphEdge.target_node_id == doc_node_id,
            GraphEdge.edge_type_id == etype.id,
            GraphEdge.tenant_key == item.tenant_key,
        ).first()
        if edge:
            db.add(GraphEdgeEvidence(
                edge_id=edge.id,
                evidence_type="USER_ASSERTION",
                reference=f"link:{item_id}",
                confidence=1.0,
                created_date=_today(),
                tenant_id=item.tenant_id,
                tenant_key=item.tenant_key,
            ))
        db.commit()
    return RedirectResponse(url=f"/documents/{item_id}/edit", status_code=303)


@router.post("/{item_id}/edges/{edge_id}/edit", response_class=HTMLResponse)
def edit_document_edge(
    request: Request,
    item_id: int,
    edge_id: int,
    edge_type: str = Form(...),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    etype = db.query(GraphEdgeType).filter(GraphEdgeType.name == edge_type).first()
    if not etype:
        return RedirectResponse(url=f"/documents/{item_id}/edit", status_code=303)
    edge = db.query(GraphEdge).filter(
        GraphEdge.id == edge_id,
        GraphEdge.target_node_id == item.node_id,
    ).first()
    if edge:
        edge.edge_type_id = etype.id
        edge.updated_date = _today()
        db.commit()
    return RedirectResponse(url=f"/documents/{item_id}/edit", status_code=303)


@router.post("/{item_id}/edges/{edge_id}/delete", response_class=HTMLResponse)
def delete_document_edge(
    request: Request,
    item_id: int,
    edge_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    user = require_user(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    edge = db.query(GraphEdge).filter(
        GraphEdge.id == edge_id,
        GraphEdge.target_node_id == item.node_id,
    ).first()
    if edge:
        db.query(GraphEdgeEvidence).filter(GraphEdgeEvidence.edge_id == edge_id).delete()
        db.delete(edge)
        db.commit()
    return RedirectResponse(url=f"/documents/{item_id}/edit", status_code=303)


@router.post("/upload", response_class=HTMLResponse)
async def upload_documents(
    request: Request,
    parent_id: Optional[str] = Form(None),
    files: list[UploadFile] = File(...),
    storage_backend: str = Form("LocalServer"),
    status: str = Form("DRAFT"),
    title: str = Form(""),
    description: str = Form(""),
    part_id: str = Form(""),
    edge_type: str = Form("HAS_SPEC"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Upload files and/or a folder under `parent_id`.

    A folder selection (webkitdirectory) yields relative paths like
    "Manuals/sub/file.pdf"; each segment becomes a folder object and each leaf
    a file object. Re-uploading a file of the same name bumps its version.
    """
    user = require_user(request, db)
    tenant_id = user.tenant_id
    tenant_key = getattr(request.state, "tenant_key", None) or user.tenant_key
    parent_id = int(parent_id) if parent_id else None
    backend = storage_backend if storage_backend in ("LocalServer", "Gitea") else "LocalServer"
    st = status if status in _DOC_STATUSES else "DRAFT"
    link_edge_type = edge_type if edge_type else "HAS_SPEC"

    def _render_list_error(msg: str, code: int = 400) -> HTMLResponse:
        ctx = auth_context(request, db)
        tid = ctx["current_user"].tenant_id
        total = (
            db.query(Document)
            .filter(Document.tenant_id == tid, Document.parent_id == parent_id)
            .count()
        )
        children = (
            db.query(Document)
            .filter(Document.tenant_id == tid, Document.parent_id == parent_id)
            .order_by(Document.kind, Document.name)
            .all()
        )
        return HTMLResponse(content=render(
            "documents/list.html",
            **ctx,
            parent_id=parent_id,
            breadcrumb=_breadcrumb(db, parent_id),
            children=children,
            q="",
            page=1,
            total=total,
            pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
            categories=_DOC_CATEGORIES,
            statuses=get_settings(request).DOC_STATUSES,
            error=msg,
        ), status_code=code)

    if not files:
        return _render_list_error("no file(s) provided")

    for f in files:
        if not f.filename:
            return _render_list_error("a file with no name was provided")
        ext = Path(f.filename).suffix.lower()
        if ext not in DOC_ALLOWED_EXTENSIONS:
            return _render_list_error(
                f"disallowed extension '{ext or '(none)'}' — allowed: "
                f"{', '.join(sorted(e.lstrip('.') for e in DOC_ALLOWED_EXTENSIONS))}"
            )

    if backend == "Gitea":
        from app.git.tenant_gitea import ensure_tenant_gitea, resolve_config
        doc_cfg = resolve_config(tenant_key)
        try:
            doc_cfg = ensure_tenant_gitea(tenant_key or "")
            await asyncio.to_thread(_gitea_doc_ensure_repo, doc_cfg)
        except Exception as e:
            logger.warning("DOCUP [REPO_WARN] %s", e)
    else:
        doc_cfg = None

    link_part_id = int(part_id) if part_id.strip() else None
    link_edge_type = edge_type if edge_type else "HAS_SPEC"

    def _resolve_edge_type_id(name: str) -> Optional[int]:
        et = db.query(GraphEdgeType).filter(GraphEdgeType.name == name).first()
        return et.id if et else None

    def _resolve_part_node(pid: int) -> Optional[int]:
        part = db.query(Part).filter(Part.part_id == pid).first()
        return part.node_id if part and part.node_id else None

    def _ensure_doc_node(doc: Document) -> Optional[int]:
        if doc.node_id:
            return doc.node_id
        node = GraphNode(
            node_label=doc.title or doc.name,
            created_by=doc.created_by,
            created_date=_today(),
            tenant_id=doc.tenant_id,
            tenant_key=doc.tenant_key,
        )
        db.add(node)
        db.flush()
        doc.node_id = node.node_id
        db.add(doc)
        db.commit()
        return node.node_id

    def _create_edge(source_nid: int, target_nid: int, etype_name: str) -> bool:
        etype_id = _resolve_edge_type_id(etype_name)
        if etype_id is None:
            return False
        exists = db.query(GraphEdge).filter(
            GraphEdge.source_node_id == source_nid,
            GraphEdge.target_node_id == target_nid,
            GraphEdge.edge_type_id == etype_id,
            GraphEdge.tenant_key == tenant_key,
        ).first()
        if exists:
            return False
        db.add(GraphEdge(
            source_node_id=source_nid,
            target_node_id=target_nid,
            edge_type_id=etype_id,
            state="ACTIVE",
            created_date=_today(),
            updated_date=_today(),
            tenant_id=tenant_id,
            tenant_key=tenant_key,
        ))
        db.flush()
        edge = db.query(GraphEdge).filter(
            GraphEdge.source_node_id == source_nid,
            GraphEdge.target_node_id == target_nid,
            GraphEdge.edge_type_id == etype_id,
            GraphEdge.tenant_key == tenant_key,
        ).first()
        if edge:
            db.add(GraphEdgeEvidence(
                edge_id=edge.id,
                evidence_type="USER_ASSERTION",
                reference=f"upload:{file_name}",
                confidence=1.0,
                created_date=_today(),
                tenant_id=tenant_id,
                tenant_key=tenant_key,
            ))
        db.commit()
        return True

    created_files = 0
    updated_files = 0
    created_folders = 0
    linked = False
    try:
        for f in files:
            content = await f.read()
            rel = (f.filename or "").replace("\\", "/")
            segments = rel.split("/")
            file_name = segments[-1]
            folder_segments = segments[:-1]

            cur_parent = parent_id
            for seg in folder_segments:
                folder, folder_is_new = _get_or_create_folder(
                    db, cur_parent, seg, tenant_id, user.user_id, tenant_key, backend
                )
                if folder_is_new:
                    created_folders += 1
                    folder.status = st
                    if description:
                        folder.description = description
                cur_parent = folder.id

            file_doc, is_new = _upsert_file(db, cur_parent, file_name, tenant_id, user.user_id, tenant_key, backend)
            if is_new:
                created_files += 1
            else:
                updated_files += 1
                file_doc.doc_version = _bump_version(file_doc.doc_version)

            file_doc.status = st
            file_doc.title = title or file_name
            if description:
                file_doc.description = description
            if not file_doc.doc_format:
                file_doc.doc_format = Path(file_name).suffix.lstrip(".").upper() or None

            if backend == "LocalServer":
                local_path = _store_document_locally(content, cur_parent, file_name, tenant_id)
                file_doc.git_repo_path = local_path
                file_doc.file_size_bytes = len(content)
                file_doc.file_checksum = hashlib.md5(content).hexdigest()
            else:
                repo_path = _compute_repo_path(db, file_doc)
                raw_url, commit_sha, size = await asyncio.to_thread(
                    _gitea_doc_put, content, repo_path, doc_cfg
                )
                file_doc.git_repo_path = repo_path
                file_doc.git_commit_sha = commit_sha
                file_doc.file_size_bytes = size
                file_doc.file_checksum = hashlib.md5(content).hexdigest()

            file_doc.modified_date = _today()
            db.flush()

            if link_part_id and not linked:
                part_node_id = _resolve_part_node(link_part_id)
                doc_node_id = _ensure_doc_node(file_doc)
                if part_node_id and doc_node_id:
                    _create_edge(part_node_id, doc_node_id, link_edge_type)
                    linked = True

        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("DOCUP [FAIL] %s", e)
        detail = getattr(getattr(e, "response", None), "text", str(e))
        return _render_list_error(f"Upload failed: {detail}", code=502)

    logger.info(
        "DOCUP [DONE] tenant=%s parent=%s new_files=%d updated=%d new_folders=%d backend=%s",
        tenant_id, parent_id, created_files, updated_files, created_folders, backend,
    )
    redirect_url = "/documents" + (f"?parent_id={parent_id}" if parent_id is not None else "")
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/{item_id}/download", response_class=HTMLResponse)
def document_download(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)

    from app.downloads.proxy import file_response
    from app.downloads.zips import zip_cache_key, zip_response
    cfg = _gitea_doc_cfg(request)
    safe_name = re.sub(r"[^A-Za-z0-9_.\-]", "_", item.name)

    # Single file → resumable (Range-aware) proxy of the private repo blob.
    if item.kind == "file":
        if item.storage_backend == "LocalServer" and item.git_repo_path:
            path = Path(item.git_repo_path)
            if not path.exists():
                return HTMLResponse(
                    content=render("404.html", **ctx, error="Local file not found."),
                    status_code=404,
                )
            return FileResponse(
                path=str(path),
                filename=safe_name,
                media_type="application/octet-stream",
            )
        if not item.git_repo_path:
            return HTMLResponse(
                content=render("404.html", **ctx, error="No storage path recorded for this file."),
                status_code=404,
            )
        return file_response(
            request, cfg, cfg.repo_docs, item.git_repo_path,
            total=item.file_size_bytes or 0,
            etag=item.git_commit_sha or "",
            filename=safe_name,
        )

    # Folder → zip all descendant files preserving the relative structure. The
    # zip is cached to disk once and served with HTTP Range so the browser can
    # pause and resume the download.
    descendants = _collect_file_descendants(db, item)
    if not descendants:
        return HTMLResponse(
            content=render("404.html", **ctx, error="This folder is empty."),
            status_code=404,
        )
    folder_path = _path_from_root(db, item)
    entries = []
    key_entries = []
    for f in descendants:
        if not f.git_repo_path:
            continue
        arcname = "/".join(_path_from_root(db, f)[len(folder_path):])
        entries.append((f.git_repo_path, arcname))
        key_entries.append((f.git_repo_path, arcname, f.git_commit_sha or ""))
    tenant_key = getattr(request.state, "tenant_key", None) or ""
    cache_key = zip_cache_key(tenant_key, "document", item.id, folder_path, key_entries)
    return zip_response(cfg, cfg.repo_docs, cache_key, entries,
                        filename=f"{safe_name}_documents.zip")


@router.get("/{item_id}/history", response_class=HTMLResponse)
def document_history(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)

    commits = []
    if item.kind == "file" and item.git_repo_path:
        from app.git.tenant_gitea import list_commits
        cfg = _gitea_doc_cfg(request)
        try:
            commits = list_commits(cfg, cfg.repo_docs, item.git_repo_path)
        except Exception as e:
            logger.warning("DOCHIST [WARN] %s", e)

    return HTMLResponse(content=render(
        "documents/history.html",
        **ctx,
        item=item,
        commits=commits,
        breadcrumb=_breadcrumb(db, item.parent_id),
    ))


@router.post("/{item_id}/delete", response_class=HTMLResponse)
def document_delete(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    require_user(request, db)
    item = db.query(Document).filter(Document.id == item_id).first()
    parent_id = item.parent_id if item else None
    if item:
        # Collect descendant ids (leaves first) for safe deletion.
        descendants = _collect_file_descendants(db, item) if item.kind == "folder" else []
        direct_children = (
            db.query(Document).filter(Document.parent_id == item.id).all()
            if item.kind == "folder" else []
        )
        # Best-effort cleanup for files.
        doc_cfg = _gitea_doc_cfg(request)
        for f in descendants:
            if f.storage_backend == "LocalServer" and f.git_repo_path:
                try:
                    Path(f.git_repo_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning("DOCDEL [LOCAL_WARN] %s: %s", f.git_repo_path, e)
            elif f.git_repo_path:
                try:
                    _gitea_doc_delete(f.git_repo_path, doc_cfg)
                except Exception as e:
                    logger.warning("DOCDEL [GIT_WARN] %s: %s", f.git_repo_path, e)
        # Delete files first, then empty subfolders, then the node itself.
        for f in descendants:
            db.delete(f)
        for c in direct_children:
            if c.kind == "folder":
                db.delete(c)
        db.delete(item)
        db.commit()
    return RedirectResponse(url=f"/documents?parent_id={parent_id or ''}", status_code=303)
