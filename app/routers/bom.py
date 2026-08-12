"""BOM router."""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.database import TenantScopedSession
from app.models import BomItem, User, Part
from app.config import DEFAULT_PAGE_SIZE
from app.routers.auth import require_user, require_role, auth_context, get_tenant_db, get_settings
from app.template_utils import render

router = APIRouter(prefix="/bom")


@router.get("", response_class=HTMLResponse)
def list_bom(
    request: Request,
    q: Optional[str] = Query(None, description="Search by part number or name"),
    bom_type: Optional[str] = Query(None, description="Filter by BOM type"),
    view: Optional[str] = Query("tree", description="View mode: tree or flat"),
    page: int = Query(1, ge=1),
    db: TenantScopedSession = Depends(get_tenant_db),
):
    """List all BOM items with collapsible tree view (default) or flat table."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    query = db.query(BomItem).options(selectinload(BomItem.part))

    if q:
        query = query.filter(
            or_(
                BomItem.part_number.ilike(f"%{q}%"),
                BomItem.part_name.ilike(f"%{q}%"),
            )
        )
    if bom_type:
        query = query.filter(BomItem.bom_type == bom_type)

    total = query.count()
    offset = (page - 1) * DEFAULT_PAGE_SIZE
    all_items = query.order_by(BomItem.level, BomItem.part_number).all()
    items = all_items[offset:offset + DEFAULT_PAGE_SIZE]

    # Build tree from the full query result set
    tree = _build_tree(all_items)

    return HTMLResponse(content=render(
        "bom/list.html",
        **ctx,
        items=items,
        tree=tree,
        tree_total=len(all_items),
        page=page,
        total=total,
        pages=(total + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        q=q or "",
        bom_type_filter=bom_type or "",
        view_mode=view or "tree",
        bom_types=get_settings(request).BOM_TYPES,
    ))


@router.get("/new", response_class=HTMLResponse)
def bom_new_form(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show BOM item creation form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "bom/new.html", **ctx,
        bom_types=get_settings(request).BOM_TYPES,
    ))


@router.post("/new", response_class=HTMLResponse)
def bom_new_submit(
    request: Request,
    part_number: str = Form(...),
    part_revision: str = Form(""),
    part_name: str = Form(""),
    level: int = Form(0),
    qty: int = Form(1),
    uom: str = Form("EA"),
    parent_assembly: str = Form(""),
    material_notes: str = Form(""),
    bom_type: str = Form("DESIGN"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Create new BOM item."""
    user = require_user(request, db)
    item = BomItem(
        part_number=part_number,
        part_revision=part_revision or None,
        part_name=part_name or None,
        level=level,
        qty=qty,
        uom=uom or "EA",
        parent_assembly=parent_assembly or None,
        material_notes=material_notes or None,
        bom_type=bom_type or "DESIGN",
        tenant_id=1,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url=f"/bom/{item.id}", status_code=303)


def parse_indented_bom(text: str):
    """Parse indented text into BOM nodes.

    Returns (nodes, errors). ``nodes`` is a list of dicts with keys:
    line, part_number, qty, uom, level, parent (parent part_number or None).
    ``errors`` is a list of human-readable strings. Leading whitespace
    (tabs or spaces) defines hierarchy (Python-style indentation stack).
    """
    nodes: List[Dict] = []
    errors: List[str] = []
    stack: List[tuple] = []  # (indent_width, part_number)
    root_count = 0

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip())
        tokens = raw.strip().split()
        pn = tokens[0]
        qty = 1
        uom = "EA"
        if len(tokens) >= 2:
            try:
                qty = int(tokens[1])
            except ValueError:
                errors.append(f"Line {lineno}: invalid quantity '{tokens[1]}' (must be an integer)")
                qty = 1
        if len(tokens) >= 3:
            uom = tokens[2]

        # Resolve parent via indentation stack
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1] if stack else None
        level = len(stack)

        if parent is None:
            root_count += 1

        nodes.append({
            "line": lineno,
            "part_number": pn,
            "qty": qty,
            "uom": uom,
            "level": level,
            "parent": parent,
        })
        stack.append((indent, pn))

    if root_count != 1:
        errors.append(f"Expected exactly 1 top-level (assembly) line, found {root_count}.")

    return nodes, errors


def validate_indented_bom(text: str, db: Session):
    """Parse and validate an indented BOM against the Parts catalog.

    Single source of truth shared by both the verify (pre-flight) and create
    endpoints so they can never disagree. Returns (nodes, parse_errors, missing)
    where ``missing`` is a sorted list of referenced part_numbers that do not
    exist as Parts.
    """
    nodes, parse_errors = parse_indented_bom(text)
    missing: List[str] = []
    if not parse_errors:
        referenced = {n["part_number"] for n in nodes}
        existing = {
            p.part_number
            for p in db.query(Part.part_number).filter(Part.part_number.in_(referenced)).all()
        }
        missing = sorted(referenced - existing)
    return nodes, parse_errors, missing


@router.get("/hierarchy", response_class=HTMLResponse)
def bom_hierarchy_form(
    request: Request,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show the indented-paste hierarchical BOM builder."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    return HTMLResponse(content=render(
        "bom/hierarchy.html", **ctx,
        bom_types=get_settings(request).BOM_TYPES,
    ))


@router.post("/hierarchy", response_class=HTMLResponse)
def bom_hierarchy_submit(
    request: Request,
    bom_text: str = Form(...),
    bom_type: str = Form("DESIGN"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Parse an indented BOM and create BomItem rows in one transaction."""
    user = require_user(request, db)
    ctx = auth_context(request, db)

    nodes, parse_errors, missing = validate_indented_bom(bom_text, db)

    # Surface missing parts with their line numbers (same validation as verify).
    errors = list(parse_errors)
    for n in nodes:
        if n["part_number"] in missing:
            errors.append(f"Line {n['line']}: unknown part '{n['part_number']}' (must exist as a Part)")

    if errors:
        return HTMLResponse(content=render(
            "bom/hierarchy.html", **ctx,
            bom_types=get_settings(request).BOM_TYPES,
            error=errors,
            submitted=bom_text,
        ))

    # Single transaction: assembly root + components
    root = nodes[0]
    items = [BomItem(
        part_number=root["part_number"],
        level=0,
        parent_assembly=None,
        qty=1,
        uom="EA",
        bom_type=bom_type or "DESIGN",
        tenant_id=1,
    )]
    for n in nodes[1:]:
        items.append(BomItem(
            part_number=n["part_number"],
            level=n["level"],
            parent_assembly=n["parent"],
            qty=n["qty"],
            uom=n["uom"],
            bom_type=bom_type or "DESIGN",
            tenant_id=1,
        ))
    db.add_all(items)
    db.commit()
    return RedirectResponse(url=f"/bom/tree/{root['part_number']}", status_code=303)


@router.post("/hierarchy/verify", response_class=JSONResponse)
def bom_hierarchy_verify(
    request: Request,
    bom_text: str = Form(...),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Check that every part in the pasted BOM already exists; report missing ones.

    Returns JSON: {"ok": bool, "parse_errors": [..], "missing": [part_number..]}.
    Does not create anything — purely a pre-flight check for the builder UI.
    """
    require_user(request, db)
    nodes, parse_errors, missing = validate_indented_bom(bom_text, db)
    return JSONResponse({"ok": not parse_errors and not missing, "parse_errors": parse_errors, "missing": missing})


@router.get("/{item_id}", response_class=HTMLResponse)
def bom_detail(request: Request, item_id: int, db: TenantScopedSession = Depends(get_tenant_db)):
    """Show BOM item detail."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(BomItem).filter(BomItem.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render("bom/detail.html", **ctx, item=item))


@router.get("/{item_id}/edit", response_class=HTMLResponse)
def bom_edit_form(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Show BOM item edit form."""
    user = require_user(request, db)
    ctx = auth_context(request, db)
    item = db.query(BomItem).filter(BomItem.id == item_id).first()
    if not item:
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    return HTMLResponse(content=render(
        "bom/edit.html", **ctx, item=item,
        bom_types=get_settings(request).BOM_TYPES,
    ))


@router.post("/{item_id}/edit", response_class=HTMLResponse)
def bom_edit_submit(
    request: Request,
    item_id: int,
    part_number: str = Form(...),
    part_revision: str = Form(""),
    part_name: str = Form(""),
    level: int = Form(0),
    qty: int = Form(1),
    uom: str = Form("EA"),
    parent_assembly: str = Form(""),
    material_notes: str = Form(""),
    bom_type: str = Form("DESIGN"),
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Update BOM item and redirect."""
    user = require_user(request, db)
    item = db.query(BomItem).filter(BomItem.id == item_id).first()
    if not item:
        ctx = auth_context(request, db)
        return HTMLResponse(content=render("404.html", **ctx), status_code=404)
    item.part_number = part_number
    item.part_revision = part_revision or None
    item.part_name = part_name or None
    item.level = level
    item.qty = qty
    item.uom = uom or "EA"
    item.parent_assembly = parent_assembly or None
    item.material_notes = material_notes or None
    item.bom_type = bom_type or "DESIGN"
    db.commit()
    return RedirectResponse(url=f"/bom/{item_id}", status_code=303)


@router.post("/{item_id}/delete", response_class=HTMLResponse)
def bom_delete(
    request: Request,
    item_id: int,
    db: TenantScopedSession = Depends(get_tenant_db),
    _role: User = Depends(require_role(["author"])),
):
    """Delete a BOM item and redirect to the list."""
    user = require_user(request, db)
    item = db.query(BomItem).filter(BomItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/bom", status_code=303)


def _build_tree(items: List[Any]) -> List[Dict]:
    """Build a recursive tree from flat BOM items ordered by level."""
    # Group items by parent_assembly
    children_map: Dict[Optional[str], List[Any]] = {}
    for item in items:
        parent = item.parent_assembly
        if parent not in children_map:
            children_map[parent] = []
        children_map[parent].append(item)

    def _make_node(item: Any) -> Dict:
        node = {
            "item": item,
            "children": [],
        }
        sub_items = children_map.get(item.part_number, [])
        # Sort children by level then part_number
        sub_items.sort(key=lambda x: (x.level, x.part_number))
        for child in sub_items:
            node["children"].append(_make_node(child))
        return node

    # Root items are those at the lowest level (typically level 0)
    # or items whose parent_assembly equals the root part_number
    roots = children_map.get(None, [])
    # Also find items that have no parent in our items list (orphans)
    all_part_numbers = {item.part_number for item in items}
    for item in items:
        parent = item.parent_assembly
        if parent is not None and parent not in all_part_numbers:
            roots.append(item)

    roots.sort(key=lambda x: (x.level, x.part_number))

    tree = []
    for root in roots:
        tree.append(_make_node(root))
    return tree


@router.get("/tree/{part_number}", response_class=HTMLResponse)
def bom_tree(request: Request, part_number: str, db: TenantScopedSession = Depends(get_tenant_db)):
    """Show hierarchical BOM tree for a top-level assembly (full subtree)."""
    user = require_user(request, db)
    ctx = auth_context(request, db)

    # Collect the full subtree rooted at part_number: the assembly's own row
    # (if any) plus every descendant reached by following parent_assembly links.
    items = []
    seen_ids = set()
    visited_parts = set()
    frontier = [part_number]
    while frontier:
        current = frontier.pop()
        if current in visited_parts:
            continue
        visited_parts.add(current)
        rows = (
            db.query(BomItem)
            .options(selectinload(BomItem.part))
            .filter((BomItem.part_number == current) | (BomItem.parent_assembly == current))
            .order_by(BomItem.level, BomItem.part_number)
            .all()
        )
        for row in rows:
            if row.id not in seen_ids:
                seen_ids.add(row.id)
                items.append(row)
                if row.part_number != current:
                    frontier.append(row.part_number)

    tree = _build_tree(items)

    return HTMLResponse(content=render(
        "bom/tree.html",
        **ctx,
        root_part_number=part_number,
        items=items,
        tree=tree,
    ))
