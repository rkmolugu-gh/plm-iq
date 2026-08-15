"""Graph traversal service (domain-tabular) for the PLM-IQ relationship UI.

Builds a collapsible, hierarchical traversal of a business object's connectivity
by deriving edges directly from existing domain tables (parts, bom, ECOs, AML/AVL,
CAD, documents). This is the relationship layer surfaced to the UI today; it mirrors
the node/edge vocabulary (PART, ECO, SUPPLIER, CAD_MODEL, DOCUMENT, HAS_COMPONENT,
AFFECTS, ...) that the future plmiq_node/plmiq_edge graph layer will formalize
(see docs/plm-iq-graph-concepts.txt).

Every query runs on the tenant-scoped session from get_tenant_db(), so traversal is
isolated per tenant.
"""

from __future__ import annotations

from typing import Optional

from app.models import (
    Part,
    BomItem,
    EngineeringChangeOrder,
    ApprovedManufacturer,
    ApprovedVendor,
    CadMetadata,
    Document,
)


def resolve_root(db, object_id: str) -> Optional[tuple[str, str, str]]:
    """Find the business object for an id and return (object_type, key, label).

    Returns None when the id matches no node-capable object.
    """
    # PART first (the primary hub type).
    part = db.query(Part).filter(Part.part_number == object_id).first()
    if part:
        return ("PART", part.part_number, part.part_name or part.part_number)

    eco = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == object_id).first()
    if eco:
        return ("ECO", eco.eco_number, eco.eco_title or eco.eco_number)

    doc = db.query(Document).filter(Document.name == object_id).first()
    if doc:
        return ("DOCUMENT", str(doc.id), doc.title or doc.name)

    cad = db.query(CadMetadata).filter(CadMetadata.cad_file_name == object_id).first()
    if cad:
        return ("CAD_MODEL", str(cad.id), cad.cad_file_name)

    aml = (
        db.query(ApprovedManufacturer)
        .filter(ApprovedManufacturer.manufacturer_name == object_id)
        .first()
    )
    if aml:
        return ("SUPPLIER", f"AML:{aml.manufacturer_name}", aml.manufacturer_name)

    avl = (
        db.query(ApprovedVendor)
        .filter(ApprovedVendor.vendor_name == object_id)
        .first()
    )
    if avl:
        return ("SUPPLIER", f"AVL:{avl.vendor_name}", avl.vendor_name)

    return None


def _label(db, object_type: str, key: str) -> str:
    """A short display label for a node corresponding to object_type/key."""
    if object_type == "PART":
        p = db.query(Part.part_name).filter(Part.part_number == key).first()
        return p[0] if p and p[0] else key
    if object_type == "ECO":
        e = db.query(EngineeringChangeOrder.eco_title).filter(EngineeringChangeOrder.eco_number == key).first()
        return e[0] if e and e[0] else key
    if object_type == "SUPPLIER":
        return key.split(":", 1)[1] if ":" in key else key
    return key


def node_edges(db, object_type: str, key: str) -> list[dict]:
    """Return the direct neighbors of a node as edge dicts.

    Each entry: {edge_type, direction, node_type, node_key, label}
    direction is 'out' (downstream from this node) or 'in' (upstream).
    """
    edges: list[dict] = []

    def add(edge_type, direction, node_type, node_key, label):
        edges.append({
            "edge_type": edge_type,
            "direction": direction,
            "node_type": node_type,
            "node_key": node_key,
            "label": label,
        })

    if object_type == "PART":
        # Children (assembly -> component) via BOM parent_assembly.
        children = (
            db.query(BomItem.part_number, BomItem.qty)
            .filter(BomItem.parent_assembly == key)
            .all()
        )
        for child_number, qty in children:
            add("HAS_COMPONENT" if qty else "HAS_COMPONENT", "out", "PART", child_number,
                f"{_label(db, 'PART', child_number)}  (x{qty})" if qty else _label(db, "PART", child_number))

        # Parents (part used in assembly) via BOM part_number.
        parents = (
            db.query(BomItem.parent_assembly)
            .filter(BomItem.part_number == key, BomItem.parent_assembly.isnot(None))
            .all()
        )
        seen_parents = set()
        for (parent_number,) in parents:
            if parent_number in seen_parents:
                continue
            seen_parents.add(parent_number)
            add("USED_IN", "in", "PART", parent_number, _label(db, "PART", parent_number))

        # ECOs affecting this part.
        ecos = (
            db.query(EngineeringChangeOrder.eco_number, EngineeringChangeOrder.eco_title)
            .filter(EngineeringChangeOrder.part_number == key)
            .all()
        )
        for eco_number, title in ecos:
            add("AFFECTS", "in", "ECO", eco_number, title or eco_number)

        # Manufacturers (AML) for this part.
        amls = (
            db.query(ApprovedManufacturer.manufacturer_name)
            .filter(ApprovedManufacturer.part_number == key)
            .all()
        )
        for (mfr,) in amls:
            add("HAS_SUPPLIER", "out", "SUPPLIER", f"AML:{mfr}", mfr)

        # Vendors (AVL) for this part.
        avls = (
            db.query(ApprovedVendor.vendor_name)
            .filter(ApprovedVendor.part_number == key)
            .all()
        )
        for (vendor,) in avls:
            add("HAS_VENDOR", "out", "SUPPLIER", f"AVL:{vendor}", vendor)

        # CAD models for this part.
        cads = (
            db.query(CadMetadata.id, CadMetadata.cad_file_name)
            .filter(CadMetadata.part_number == key)
            .all()
        )
        for cad_id, fname in cads:
            add("HAS_CAD", "out", "CAD_MODEL", str(cad_id), fname)

        # Documents linked to this part (matched by name prefix, when available).
        docs = (
            db.query(Document.id, Document.name, Document.title)
            .filter(Document.name.like(f"{key}%"))
            .all()
        )
        for doc_id, name, title in docs:
            add("HAS_DOCUMENT", "out", "DOCUMENT", str(doc_id), title or name)

    elif object_type == "ECO":
        # ECO affects a part.
        ev = _label(db, "PART", key)
        eco_obj = db.query(EngineeringChangeOrder).filter(EngineeringChangeOrder.eco_number == key).first()
        if eco_obj and eco_obj.part_number:
            add("AFFECTS", "out", "PART", eco_obj.part_number, _label(db, "PART", eco_obj.part_number))

    elif object_type == "SUPPLIER":
        kind, name = (key.split(":", 1) + [""])[:2] if ":" in key else ("AML", key)
        if kind == "AML":
            rows = (
                db.query(ApprovedManufacturer.part_number)
                .filter(ApprovedManufacturer.manufacturer_name == name)
                .all()
            )
            for (pn,) in rows:
                add("SUPPLIES", "out", "PART", pn, _label(db, "PART", pn))
        else:
            rows = (
                db.query(ApprovedVendor.part_number)
                .filter(ApprovedVendor.vendor_name == name)
                .all()
            )
            for (pn,) in rows:
                add("SUPPLIES", "out", "PART", pn, _label(db, "PART", pn))

    elif object_type == "CAD_MODEL":
        try:
            cad_id = int(key)
        except (TypeError, ValueError):
            cad_id = None
        if cad_id is not None:
            row = db.query(CadMetadata.part_number).filter(CadMetadata.id == cad_id).first()
            if row and row[0]:
                add("BELONGS_TO", "out", "PART", row[0], _label(db, "PART", row[0]))

    elif object_type == "DOCUMENT":
        try:
            doc_id = int(key)
        except (TypeError, ValueError):
            doc_id = None
        if doc_id is not None:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc and doc.name:
                # Documents are stored by part prefix when seeded; link to that part.
                add("REFERENCES", "out", "PART", doc.name, doc.name)

    return edges


def build_tree(db, object_id: str, max_depth: int = 8, max_nodes: int = 400) -> Optional[dict]:
    """Return a nested traversal tree rooted at object_id, or None if unknown.

    Tree node shape: {node_type, key, label, edge_type, direction, expanded, children}
    Children are limited by a global node cap and a per-path cycle guard.
    """
    root_info = resolve_root(db, object_id)
    if root_info is None:
        return None
    rtype, rkey, rlabel = root_info

    total = {"n": 0}

    def build(node_type, key, label, edge_type, direction, depth, path) -> Optional[dict]:
        if total["n"] >= max_nodes:
            return None
        total["n"] += 1
        node = {
            "node_type": node_type,
            "key": str(key),
            "label": label,
            "edge_type": edge_type,
            "direction": direction,
            "expanded": True,
            "children": [],
        }
        if depth >= max_depth:
            return node
        branch_key = (node_type, str(key))
        if branch_key in path:
            return node
        path = path | {branch_key}
        for e in node_edges(db, node_type, str(key)):
            child = build(e["node_type"], e["node_key"], e["label"],
                          e["edge_type"], e["direction"], depth + 1, path)
            if child is not None:
                node["children"].append(child)
            if total["n"] >= max_nodes:
                break
        return node

    root = build(rtype, rkey, rlabel, None, None, 0, frozenset())
    if root is not None:
        root["label"] = rlabel
    return root


def tree_to_lines(root: dict) -> list[str]:
    """Flatten the tree into indented, hierarchical text lines for export."""
    lines: list[str] = []

    def walk(node, depth):
        indent = "  " * depth
        if node["edge_type"]:
            via = f"  <-[{node['edge_type']} {node['direction'].upper()}]"
        else:
            via = ""
        marker = "*" if depth == 0 else ""
        label = node["label"].replace("\n", " ")
        lines.append(f"{indent}{marker} [{node['node_type']}] {label}{via}")
        for child in node["children"]:
            walk(child, depth + 1)

    walk(root, 0)
    return lines
