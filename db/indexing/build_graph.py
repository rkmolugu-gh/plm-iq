"""Backfill the graph layer (plmiq_*) from existing PLM-IQ domain data.

Phase 2 of the graph roadmap (see docs/plm-iq-graph-concepts.txt). Registers
existing domain rows as plmiq_node identities and derives edges from the
existing relational links — it does NOT invent new relationships.

Edges are stored once in their canonical direction (per GRAPH GOVERNANCE items
1 and 2); the inverse traversal is obtained from plmiq_edge_type.inverse_type,
never by duplicating the edge. Every derived structural edge gets one
plmiq_edge_evidence row pointing at the source domain record, marked as human /
structural (author_type, confidence 1.0), distinct from future AI-inferred edges.

Run with:
    python -m db.indexing.build_graph [--force]

--force clears the six plmiq_* tables first (a fresh full rebuild of the graph
layer). Without --force it is incremental: existing node_id links are reused
and new rows are appended.

This is a build/admin script and runs over all tenants (like build_all.py); the
app runtime never mutates the graph through these tables directly.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Part,
    BomItem,
    CostingBomItem,
    EngineeringChangeOrder,
    ApprovedManufacturer,
    ApprovedVendor,
    CadMetadata,
    Document,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowTask,
    User,
    Tenant,
    GraphNode,
    GraphEdgeType,
    GraphEdge,
    GraphEdgeEvidence,
)

logger = logging.getLogger(__name__)

_TABLES = [
    "parts",
    "costing_bom",
    "engineering_change_orders",
    "approved_manufacturer_list",
    "approved_vendor_list",
    "cad_metadata",
    "documents",
    "workflow_definitions",
    "workflow_instances",
    "workflow_tasks",
    "users",
    "tenants",
]

_NOW = None  # set once in build() (Date.now disallowed in workflow scripts only)


def _now() -> str:
    return datetime.now().strftime("%d-%m-%Y")


# ----------------------------------------------------------------------
# Node sources — (model, object_type, key, label, created_by, label_kind)
# key/label/created_by are callables taking a row. label_kind='str' uses
# label(row); 'str_or_key' falls back to key(row).
# ----------------------------------------------------------------------
def _cb(row):  # created_by accessor that tolerates models without the attr
    return getattr(row, "created_by", None)


NODE_SOURCES = [
    (Tenant, "ORGANIZATION", lambda r: r.tenant_id, lambda r: r.tenant_name, lambda r: None),
    (User, "USER", lambda r: r.user_id, lambda r: r.username or r.full_name, lambda r: None),
    (Part, "PART", lambda r: r.part_number, lambda r: r.part_name, _cb),
    (CostingBomItem, "COST", lambda r: r.id,
     lambda r: f"Cost {r.part_number} L{r.level}", _cb),
    (EngineeringChangeOrder, "ENGINEERING_CHANGE", lambda r: r.eco_number,
     lambda r: r.eco_title, _cb),
    (ApprovedManufacturer, "SUPPLIER", lambda r: r.id,
     lambda r: f"MFR:{r.manufacturer_name}", _cb),
    (ApprovedVendor, "SUPPLIER", lambda r: r.id,
     lambda r: f"VND:{r.vendor_name}", _cb),
    (CadMetadata, "CAD_MODEL", lambda r: r.id, lambda r: r.cad_file_name, _cb),
    (Document, "DOCUMENT", lambda r: r.id, lambda r: r.title or r.name, _cb),
    (WorkflowDefinition, "WORKFLOW", lambda r: r.id, lambda r: r.name,
     lambda r: getattr(r, "created_by", None)),
    (WorkflowInstance, "WORKFLOW_INSTANCE", lambda r: r.id, lambda r: r.object_id, lambda r: None),
    (WorkflowTask, "WORKFLOW_TASK", lambda r: r.id, lambda r: r.step_name, lambda r: None),
]


def _clear_graph(db: Session) -> None:
    """Remove all graph-layer rows (FK order matters).

    The identity registry (plmiq_node) is referenced by the UNIQUE node_id FK
    carried on every node-capable domain table. Before deleting nodes we must
    release those FKs (set them to NULL on the domain rows); otherwise SQLite's
    foreign-key enforcement blocks the DELETE. The domain rows are re-registered
    and re-linked during _build_nodes.
    """
    for model, _otype, _kf, _lf, _cf in NODE_SOURCES:
        db.query(model).update({model.node_id: None})
    db.flush()
    db.query(GraphEdgeEvidence).delete()
    db.query(GraphEdge).delete()
    db.query(GraphNode).delete()


def _edge_type_ids(db: Session) -> dict[str, int]:
    """Map edge-type name -> id from the governed catalog."""
    return {et.name: et.id for et in db.query(GraphEdgeType).all()}


def _build_nodes(db: Session) -> dict:
    """Insert a plmiq_node for every node-capable domain row; set row.node_id.

    Returns counts by object_type and a set of node_ids created.
    """
    counts: dict[str, int] = {}
    created: set[int] = set()
    for model, otype, key_fn, label_fn, created_by_fn in NODE_SOURCES:
        rows = db.query(model).all()
        n = 0
        for row in rows:
            if getattr(row, "node_id", None) is not None:
                continue  # already registered (idempotent)
            node = GraphNode(
                node_label=str(label_fn(row) or key_fn(row)),
                created_by=created_by_fn(row),
                created_date=_now(),
                tenant_id=getattr(row, "tenant_id", None) or 1,
                tenant_key=getattr(row, "tenant_key", None) or "plm-iq",
            )
            db.add(node)
            db.flush()  # assign node.node_id
            row.node_id = node.node_id
            db.add(row)
            created.add(node.node_id)
            n += 1
        db.commit()
        counts[otype] = counts.get(otype, 0) + n
        logger.info("  nodes[%s]: %d new", otype, n)
    return counts, created


def _add_edge(
    db: Session,
    source: int,
    target: int,
    edge_type_id: int,
    evidence_type: str,
    evidence_ref: str,
    *,
    quantity=None,
    unit=None,
    attrs=None,
) -> None:
    """Insert one canonical-direction edge plus its structural evidence row."""
    # Normalize tenant from the source node so the edge is tenanted. This MUST be
    # resolved before the edge is flushed: both tenant_id and tenant_key are
    # NOT NULL on plmiq_edge, so a deferred (None) flush would violate the
    # constraint.
    src = db.get(GraphNode, source)
    src_tenant_id = src.tenant_id if src is not None else 1
    src_tenant_key = src.tenant_key if src is not None else "plm-iq"
    edge = GraphEdge(
        source_node_id=source,
        target_node_id=target,
        edge_type_id=edge_type_id,
        state="ACTIVE",
        quantity=quantity,
        unit=unit,
        attributes=attrs,
        created_date=_now(),
        updated_date=_now(),
        tenant_id=src_tenant_id,
        tenant_key=src_tenant_key,
    )
    db.add(edge)
    db.flush()  # assign edge.id
    db.add(GraphEdgeEvidence(
        edge_id=edge.id,
        evidence_type=evidence_type,
        reference=evidence_ref,
        confidence=1.0,  # structural / human-source, not AI inference
        created_date=_now(),
        tenant_id=src_tenant_id,
        tenant_key=src_tenant_key,
    ))
    db.commit()


def _part_node(db: Session, part_number: str) -> Optional[int]:
    row = db.query(Part).filter(Part.part_number == part_number).first()
    return row.node_id if row and row.node_id else None


def _derive_edges(db: Session, edge_ids: dict[str, int]) -> dict:
    """Derive canonical edges from existing relational links (Phase 2 body)."""
    stats = {name: 0 for name in edge_ids}

    def emit(name, source, target, ev_type, ev_ref, **kw):
        if name not in edge_ids or source is None or target is None:
            return
        _add_edge(db, source, target, edge_ids[name], ev_type, ev_ref, **kw)
        stats[name] = stats.get(name, 0) + 1

    _EVID = {
        "HAS_COMPONENT": "BOM_RECORD",
        "HAS_COST": "SOURCE_OBJECT",
        "AFFECTS": "WORKFLOW_RECORD",
        "HAS_SUPPLIER": "SUPPLIER_RECORD",
        "HAS_VENDOR": "SUPPLIER_RECORD",
        "HAS_CAD": "SOURCE_OBJECT",
        "HAS_DOCUMENT": "SOURCE_OBJECT",
        "OPERATES_ON": "WORKFLOW_RECORD",
        "ASSIGNED_TO": "WORKFLOW_RECORD",
        "OWNS": "SOURCE_OBJECT",
        "RESPONSIBLE_FOR": "SOURCE_OBJECT",
    }

    # Helper: look up a node by object type + business key.
    node_cache: dict[tuple[str, str], Optional[int]] = {}

    def node_for(otype: str, key) -> Optional[int]:
        if key is None:
            return None
        k = (otype, str(key))
        if k in node_cache:
            return node_cache[k]
        node_id = None
        if otype == "PART":
            node_id = _part_node(db, key)
        node_cache[k] = node_id
        return node_id

    # -- BOM structure -----------------------------------------------------
    # bom.parent_assembly is the ASSEMBLY; bom.part_number is the COMPONENT.
    seen_bom = set()
    for b in db.query(BomItem).all():
        if not b.parent_assembly:
            continue
        parent = node_for("PART", b.parent_assembly)
        child = node_for("PART", b.part_number)
        key = (parent, child)
        if key in seen_bom or parent is None or child is None:
            continue
        seen_bom.add(key)
        emit("HAS_COMPONENT", parent, child, _EVID["HAS_COMPONENT"],
             f"bom:{b.id}", quantity=b.qty, unit=b.uom,
             attrs='{"bom_id": %d}' % b.id)

    # -- Costing -----------------------------------------------------------
    for c in db.query(CostingBomItem).all():
        emit("HAS_COST", node_for("PART", c.part_number), c.node_id,
             _EVID["HAS_COST"], f"costing:{c.id}")

    # -- ECO affects its part ----------------------------------------------
    for eco in db.query(EngineeringChangeOrder).all():
        emit("AFFECTS", eco.node_id, node_for("PART", eco.part_number),
             _EVID["AFFECTS"], eco.eco_number)

    # -- AML / AVL supply --------------------------------------------------
    for aml in db.query(ApprovedManufacturer).all():
        emit("HAS_SUPPLIER", node_for("PART", aml.part_number), aml.node_id,
             _EVID["HAS_SUPPLIER"], aml.manufacturer_name)
    for avl in db.query(ApprovedVendor).all():
        emit("HAS_VENDOR", node_for("PART", avl.part_number), avl.node_id,
             _EVID["HAS_VENDOR"], avl.vendor_name)

    # -- CAD ---------------------------------------------------------------
    for cad in db.query(CadMetadata).all():
        emit("HAS_CAD", node_for("PART", cad.part_number), cad.node_id,
             _EVID["HAS_CAD"], f"cad:{cad.id}")

    # -- Documents (linked by part-number prefix, as the UI graph does) -----
    for doc in db.query(Document).all():
        if doc.kind != "file":
            continue
        pn = doc.name.split("/")[-1] or doc.name
        part = db.query(Part).filter(
            (Part.part_number == pn) | (Part.part_number == doc.name)
        ).first()
        target = part.node_id if part and part.node_id else None
        emit("HAS_DOCUMENT", target, doc.node_id, _EVID["HAS_DOCUMENT"],
             doc.name or f"doc:{doc.id}")

    # -- Workflow: instance operates on its object ---------------------------
    for wi in db.query(WorkflowInstance).all():
        obj = node_for("PART", wi.object_id) if wi.object_type in ("part", "PART") else None
        if obj is None and wi.object_type in ("eco", "ECO", "engineering_change"):
            eco_node = db.query(EngineeringChangeOrder.node_id).filter(
                EngineeringChangeOrder.eco_number == wi.object_id).first()
            obj = eco_node[0] if eco_node and eco_node[0] else None
        emit("OPERATES_ON", wi.node_id, obj, _EVID["OPERATES_ON"], f"wfi:{wi.id}")

    # -- Workflow: task assigned to a user ----------------------------------
    for wt in db.query(WorkflowTask).all():
        user = db.query(User).filter(User.user_id == wt.assigned_to).first()
        emit("ASSIGNED_TO", wt.node_id, user.node_id if user else None,
             _EVID["ASSIGNED_TO"], f"wft:{wt.id}")

    # -- Ownership: user created the part / ECO -----------------------------
    for p in db.query(Part).all():
        if p.created_by:
            u = db.query(User).filter(User.user_id == p.created_by).first()
            emit("OWNS", u.node_id if u else None, p.node_id,
                 _EVID["OWNS"], p.part_number)
    for eco in db.query(EngineeringChangeOrder).all():
        owner = eco.change_drafter or eco.created_by
        if owner:
            u = db.query(User).filter(User.user_id == owner).first()
            emit("RESPONSIBLE_FOR", u.node_id if u else None, eco.node_id,
                 _EVID["RESPONSIBLE_FOR"], eco.eco_number)

    return stats


def build(force: bool = False) -> dict:
    """Register nodes and derive edges for the whole graph layer.

    Args:
        force: If True, clear all plmiq_* rows before rebuilding.
    """
    global _NOW
    if _NOW is None:
        _NOW = _now()

    db = SessionLocal()
    try:
        if force:
            logger.info("Clearing graph layer...")
            _clear_graph(db)
        counts, _created = _build_nodes(db)
        edge_ids = _edge_type_ids(db)
        logger.info("Edge catalog: %d edge types", len(edge_ids))
        edge_stats = _derive_edges(db, edge_ids)
        n_nodes = db.query(GraphNode).count()
        n_edges = db.query(GraphEdge).count()
        n_evidence = db.query(GraphEdgeEvidence).count()
        logger.info("Graph totals: %d nodes, %d edges, %d evidence rows",
                   n_nodes, n_edges, n_evidence)
        return {
            "nodes_by_type": counts,
            "total_nodes": n_nodes,
            "edges": edge_stats,
            "total_edges": n_edges,
            "total_evidence": n_evidence,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    force = "--force" in sys.argv
    logger.info("Building graph layer (force=%s)", force)
    result = build(force=force)
    logger.info("Result: %s", result)


if __name__ == "__main__":
    main()
