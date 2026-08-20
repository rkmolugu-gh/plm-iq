"""Seed / enrich the BicycleCo tenant so every part has full graph traversal data.

Phase 2 delivers nodes/edges/evidence by DERIVING them from existing domain rows
(see build_graph.py). A part only shows up well in the graph (neighborhood,
upstream/downstream, structure, propagation) if it has relational data behind every
edge type. This script fills the gaps for the BicycleCo tenant so each of its parts
carries all edge aspects AND the evidence that build_graph attaches to each derived edge:

    edge aspect            derived from domain table       evidence_type
    HAS_COMPONENT/USED_IN  bom                        BOM_RECORD
    HAS_COST               costing_bom                 SOURCE_OBJECT
    HAS_SUPPLIER (AML)    approved_manufacturer_list SUPPLIER_RECORD
    HAS_VENDOR   (AVL)    approved_vendor_list      SUPPLIER_RECORD
    HAS_CAD               cad_metadata               SOURCE_OBJECT
    HAS_DOCUMENT          documents                 SOURCE_OBJECT
    AFFECTS              engineering_change_orders   WORKFLOW_RECORD
    OPERATES_ON / ASSIGNED_TO  workflow_instances / workflow_tasks  WORKFLOW_RECORD
    OWNS / RESPONSIBLE_FOR     parts.created_by / eco.change_drafter  SOURCE_OBJECT

It is idempotent (skips rows that already exist, per tenant) and then runs the
full graph build so nodes, canonical edges and evidence are regenerated.

Run with:
    python -m db.indexing.graph_seed [--no-build]

--no-build only enriches the domain data and skips the graph build.

Safe to re-run after the demo DB is rebuilt (builds are incremental unless forced).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime

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
    GraphNode,
    GraphEdge,
    GraphEdgeType,
    GraphEdgeEvidence,
)

logger = logging.getLogger(__name__)

TENANT_KEY = "tk_bicycleco_a1b2c3d4"
TENANT_ID = 1  # BicycleCo
_NOW = datetime.now().strftime("%d-%m-%Y")


def _now() -> str:
    return datetime.now().strftime("%d-%m-%Y")


def _parts(db) -> list[Part]:
    return db.query(Part).filter(Part.tenant_key == TENANT_KEY).all()


def _user(db) -> User:
    u = db.query(User).filter(User.tenant_key == TENANT_KEY,
                            User.username == "megan").first()
    if not u:
        u = db.query(User).filter(User.tenant_key == TENANT_KEY).first()
    return u


# ----------------------------------------------------------------------
# Domain enrichment (idempotent, per tenant)
# ----------------------------------------------------------------------

def _ensure_cost_rows(db) -> int:
    n = 0
    for p in _parts(db):
        exists = db.query(CostingBomItem).filter(
            CostingBomItem.part_number == p.part_number,
            CostingBomItem.tenant_key == TENANT_KEY).first()
        if exists:
            continue
        db.add(CostingBomItem(
            level=3, part_number=p.part_number, part_name=p.part_name,
            qty=1, uom=p.uom, material_cost=2.00, labor_cost=3.00,
            overhead_cost=0.75, machining_cost=1.50, unit_cost=7.25,
            extended_cost=7.25, rolled_total=7.25, cost_type='LEAF',
            created_by=p.created_by, created_date=_now(), modified_date=_now(),
            tenant_id=TENANT_ID, tenant_key=TENANT_KEY))
        n += 1
    db.commit()
    return n


def _ensure_bom(db) -> int:
    """Make sure every non-root part appears as a component (gives USED_IN)."""
    n = 0
    for p in _parts(db):
        if p.part_number == "BIKE-001":
            continue
        used_in = db.query(BomItem).filter(
            BomItem.part_number == p.part_number,
            BomItem.tenant_key == TENANT_KEY).first()
        if used_in:
            continue  # already a component somewhere
        db.add(BomItem(level=3, part_number=p.part_number,
                       part_revision=p.part_revision, part_name=p.part_name,
                       qty=1, uom=p.uom, parent_assembly="BIKE-001",
                       bom_type="DESIGN", created_by=p.created_by,
                       created_date=_now(), tenant_id=TENANT_ID, tenant_key=TENANT_KEY))
        n += 1
    db.commit()
    return n


def _ensure_cad(db) -> int:
    n = 0
    for p in _parts(db):
        exists = db.query(CadMetadata).filter(
            CadMetadata.part_number == p.part_number,
            CadMetadata.tenant_key == TENANT_KEY).first()
        if exists:
            continue
        db.add(CadMetadata(
            part_number=p.part_number, part_revision=p.part_revision,
            part_name=p.part_name, status='DRAFT',
            cad_file_name=f"{p.part_number}_{p.part_revision}.sldprt",
            cad_file_format='SLDPRT', cad_system='SolidWorks 2024',
            cad_version='2024 SP4', file_reference_type='Git',
            modeling_author=p.created_by, cad_created_date=_now(), created_date=_now(),
            drawing_number=f"DRW-{p.part_number}",
            model_type='PART', source_type='FABRICATED',
            notes='Graph seed CAD row.', created_by=p.created_by, modified_date=_now(),
            tenant_id=TENANT_ID, tenant_key=TENANT_KEY))
        n += 1
    db.commit()
    return n


def _ensure_aml(db) -> int:
    n = 0
    for p in _parts(db):
        exists = db.query(ApprovedManufacturer).filter(
            ApprovedManufacturer.part_number == p.part_number,
            ApprovedManufacturer.tenant_key == TENANT_KEY).first()
        if exists:
            continue
        db.add(ApprovedManufacturer(
            part_number=p.part_number, part_revision=p.part_revision,
            part_name=p.part_name, manufacturer_name=f"Seed Mfr {p.part_number}",
            manufacturer_part_number=f"MFR-{p.part_number}",
            manufacturer_status='APPROVED', source_type='PURCHASED',
            preferred_flag='No', lead_time_days=15, unit_cost=5.00,
            currency='USD', compliance_status='RoHS 3 Compliant',
            quality_rating='A', approval_date=_now(), notes='Graph seed AML row.',
            created_by=p.created_by, modified_by=p.created_by,
            created_date=_now(), modified_date=_now(),
            tenant_id=TENANT_ID, tenant_key=TENANT_KEY))
        n += 1
    db.commit()
    return n


def _ensure_avl(db) -> int:
    n = 0
    for p in _parts(db):
        exists = db.query(ApprovedVendor).filter(
            ApprovedVendor.part_number == p.part_number,
            ApprovedVendor.tenant_key == TENANT_KEY).first()
        if exists:
            continue
        db.add(ApprovedVendor(
            part_number=p.part_number, part_revision=p.part_revision,
            part_name=p.part_name, vendor_name=f"Seed Vendor {p.part_number}",
            vendor_site='Portland, OR, USA',
            vendor_part_number=f"VND-{p.part_number}", vendor_status='APPROVED',
            preferred_flag='No', lead_time_days=15, unit_price=5.00,
            currency='USD', min_order_qty=1, moq_uom='EA',
            iso_certified='Yes', compliance_status='RoHS 3 Compliant',
            approval_date=_now(), notes='Graph seed AVL row.',
            created_by=p.created_by, modified_by=p.created_by,
            created_date=_now(), modified_date=_now(),
            tenant_id=TENANT_ID, tenant_key=TENANT_KEY))
        n += 1
    db.commit()
    return n


def _ensure_documents(db) -> int:
    n = 0
    for p in _parts(db):
        exists = db.query(Document).filter(
            Document.name == p.part_number,
            Document.tenant_key == TENANT_KEY).first()
        if exists:
            continue
        db.add(Document(
            kind='file', name=p.part_number,
            title=f"{p.part_name} - {p.part_number} specification",
            doc_category='SPECIFICATION', doc_format='PDF',
            doc_system='PLM-IQ', doc_version='1.0', status='DRAFT',
            description=f'Graph seed demo document for {p.part_number}.',
            storage_backend='GraphSeed', created_by=p.created_by,
            modified_by=p.created_by, created_date=_now(), modified_date=_now(),
            tenant_id=TENANT_ID, tenant_key=TENANT_KEY))
        n += 1
    db.commit()
    return n


def _ensure_ecos(db) -> int:
    n = 0
    for p in _parts(db):
        exists = db.query(EngineeringChangeOrder).filter(
            EngineeringChangeOrder.part_number == p.part_number,
            EngineeringChangeOrder.tenant_key == TENANT_KEY).first()
        if exists:
            continue
        seq = _next_eco_seq(db)
        db.add(EngineeringChangeOrder(
            eco_number=f"ECO-{seq:04d}",
            eco_title=f"Seed change for {p.part_number}",
            eco_description=f'Graph seed ECO row for {p.part_number}.',
            eco_status='REVIEW', part_number=p.part_number,
            current_revision=p.part_revision, new_revision=p.part_revision,
            change_type='OTHER', change_detail='Graph seed demonstration change.',
            change_drafter=p.created_by, change_approver=p.created_by,
            drafted_date=_now(), created_by=p.created_by, created_date=_now(),
            modified_date=_now(), tenant_id=TENANT_ID, tenant_key=TENANT_KEY))
        n += 1
    db.commit()
    return n


def _next_eco_seq(db) -> int:
    nums = []
    for (eco_number,) in db.query(EngineeringChangeOrder.eco_number).filter(
            EngineeringChangeOrder.tenant_key == TENANT_KEY).all():
        try:
            nums.append(int(eco_number.split("-")[-1]))
        except ValueError:
            pass
    return (max(nums) + 1) if nums else 1


def _ensure_workflows(db) -> int:
    """One workflow instance + tasks per part (OPERATES_ON / ASSIGNED_TO)."""
    u = _user(db)
    definition = db.query(WorkflowDefinition).filter(
        WorkflowDefinition.object_type == 'part').first()
    n = 0
    for p in _parts(db):
        inst = db.query(WorkflowInstance).filter(
            WorkflowInstance.object_type == 'part',
            WorkflowInstance.object_id == p.part_number,
            WorkflowInstance.tenant_key == TENANT_KEY).first()
        if inst is None:
            inst = WorkflowInstance(
                definition_id=definition.id if definition else None,
                object_type='part', object_id=p.part_number,
                status='IN_PROGRESS', current_stage=0,
                started_by=u.user_id if u else None,
                started_at=_now(), result_status='RELEASED',
                due_date=_now(), tenant_id=TENANT_ID, tenant_key=TENANT_KEY)
            db.add(inst)
            db.flush()
            assignee = db.query(User).filter(
                User.tenant_key == TENANT_KEY,
                User.role == 'quality').first() or u
            task = WorkflowTask(
                instance_id=inst.id, stage_index=0, step_key='seed_review',
                step_name='Seeded Engineering Review',
                assigned_to=assignee.user_id if assignee else None,
                status='PENDING', action='approve',
                due_date=_now(), tenant_id=TENANT_ID, tenant_key=TENANT_KEY)
            db.add(task)
            n += 1
    db.commit()
    return n


def _ensure_doc_part_edges(db) -> int:
    """Create HAS_SPEC edges from each part to its seed document."""
    has_spec = db.query(GraphEdgeType).filter(
        GraphEdgeType.name == 'HAS_SPEC').first()
    if not has_spec:
        logger.warning("HAS_SPEC edge type not found; skipping doc-part edges")
        return 0
    n = 0
    for p in _parts(db):
        doc = db.query(Document).filter(
            Document.name == p.part_number,
            Document.tenant_key == TENANT_KEY).first()
        if not doc or not doc.node_id or not p.node_id:
            continue
        exists = db.query(GraphEdge).filter(
            GraphEdge.source_node_id == p.node_id,
            GraphEdge.target_node_id == doc.node_id,
            GraphEdge.edge_type_id == has_spec.id,
            GraphEdge.tenant_key == TENANT_KEY).first()
        if exists:
            continue
        db.add(GraphEdge(
            source_node_id=p.node_id,
            target_node_id=doc.node_id,
            edge_type_id=has_spec.id,
            state='ACTIVE',
            created_date=_now(),
            updated_date=_now(),
            tenant_id=TENANT_ID,
            tenant_key=TENANT_KEY,
        ))
        db.flush()
        edge = db.query(GraphEdge).filter(
            GraphEdge.source_node_id == p.node_id,
            GraphEdge.target_node_id == doc.node_id,
            GraphEdge.edge_type_id == has_spec.id,
            GraphEdge.tenant_key == TENANT_KEY,
        ).first()
        if edge:
            db.add(GraphEdgeEvidence(
                edge_id=edge.id,
                evidence_type='USER_ASSERTION',
                reference=f'graph_seed:{p.part_number}',
                confidence=1.0,
                created_date=_now(),
                tenant_id=TENANT_ID,
                tenant_key=TENANT_KEY,
            ))
        db.commit()
        n += 1

    # Explicitly link BB-002-N.pdf to BIKE-001 as HAS_SPEC
    bike = db.query(Part).filter(
        Part.part_number == 'BIKE-001',
        Part.tenant_key == TENANT_KEY).first()
    bb_doc = db.query(Document).filter(
        Document.name == 'BB-002-N.pdf',
        Document.tenant_key == TENANT_KEY).first()
    if bike and bb_doc and bike.node_id and bb_doc.node_id:
        exists = db.query(GraphEdge).filter(
            GraphEdge.source_node_id == bike.node_id,
            GraphEdge.target_node_id == bb_doc.node_id,
            GraphEdge.edge_type_id == has_spec.id,
            GraphEdge.tenant_key == TENANT_KEY).first()
        if not exists:
            db.add(GraphEdge(
                source_node_id=bike.node_id,
                target_node_id=bb_doc.node_id,
                edge_type_id=has_spec.id,
                state='ACTIVE',
                created_date=_now(),
                updated_date=_now(),
                tenant_id=TENANT_ID,
                tenant_key=TENANT_KEY,
            ))
            db.flush()
            edge = db.query(GraphEdge).filter(
                GraphEdge.source_node_id == bike.node_id,
                GraphEdge.target_node_id == bb_doc.node_id,
                GraphEdge.edge_type_id == has_spec.id,
                GraphEdge.tenant_key == TENANT_KEY,
            ).first()
            if edge:
                db.add(GraphEdgeEvidence(
                    edge_id=edge.id,
                    evidence_type='USER_ASSERTION',
                    reference='graph_seed:BB-002-N.pdf',
                    confidence=1.0,
                    created_date=_now(),
                    tenant_id=TENANT_ID,
                    tenant_key=TENANT_KEY,
                ))
            db.commit()
            n += 1
    return n


# ----------------------------------------------------------------------
# Top-level
# ----------------------------------------------------------------------

def _ensure_bike_eco(db) -> int:
    """Explicitly link an ECO to BIKE-001 revision H (idempotent).

    Creates the ECO row (if missing), ensures it has a graph node, and draws an
    AFFECTS edge from the ECO node to the BIKE-001/H part node so it appears in
    both the Change Orders tab and the part graph.
    """
    bike = db.query(Part).filter(
        Part.part_number == "BIKE-001",
        Part.part_revision == "H",
        Part.tenant_key == TENANT_KEY,
    ).first()
    if not bike or not bike.node_id:
        logger.warning("BIKE-001/H not found or has no node; skipping bike ECO")
        return 0

    affects = db.query(GraphEdgeType).filter(GraphEdgeType.name == "AFFECTS").first()
    if not affects:
        logger.warning("AFFECTS edge type not found; skipping bike ECO edge")
        return 0

    eco_number = "ECO-BIKE-001-H"
    eco = db.query(EngineeringChangeOrder).filter(
        EngineeringChangeOrder.eco_number == eco_number,
        EngineeringChangeOrder.tenant_key == TENANT_KEY,
    ).first()
    if eco is None:
        eco = EngineeringChangeOrder(
            eco_number=eco_number,
            eco_title="Linked change for BIKE-001 rev H",
            eco_description="Graph seed ECO explicitly linked to BIKE-001 revision H.",
            eco_status="REVIEW",
            part_number="BIKE-001",
            current_revision="H",
            new_revision="H",
            change_type="DESIGN_CHANGE",
            change_detail="Linked to BIKE-001 revision H via graph seed.",
            change_drafter=bike.created_by,
            change_approver=bike.created_by,
            drafted_date=_now(),
            created_by=bike.created_by,
            created_date=_now(),
            modified_date=_now(),
            tenant_id=TENANT_ID,
            tenant_key=TENANT_KEY,
        )
        db.add(eco)
        db.flush()

    if not eco.node_id:
        node = GraphNode(
            node_label=eco_number,
            created_by=eco.created_by,
            created_date=_now(),
            tenant_id=TENANT_ID,
            tenant_key=TENANT_KEY,
        )
        db.add(node)
        db.flush()
        eco.node_id = node.node_id
        db.add(eco)
        db.flush()

    exists = db.query(GraphEdge).filter(
        GraphEdge.source_node_id == eco.node_id,
        GraphEdge.target_node_id == bike.node_id,
        GraphEdge.edge_type_id == affects.id,
        GraphEdge.tenant_key == TENANT_KEY,
    ).first()
    if not exists:
        db.add(GraphEdge(
            source_node_id=eco.node_id,
            target_node_id=bike.node_id,
            edge_type_id=affects.id,
            state="ACTIVE",
            created_date=_now(),
            updated_date=_now(),
            tenant_id=TENANT_ID,
            tenant_key=TENANT_KEY,
        ))
        db.flush()
        edge = db.query(GraphEdge).filter(
            GraphEdge.source_node_id == eco.node_id,
            GraphEdge.target_node_id == bike.node_id,
            GraphEdge.edge_type_id == affects.id,
            GraphEdge.tenant_key == TENANT_KEY,
        ).first()
        if edge:
            db.add(GraphEdgeEvidence(
                edge_id=edge.id,
                evidence_type="WORKFLOW_RECORD",
                reference=f"graph_seed:{eco_number}",
                confidence=1.0,
                created_date=_now(),
                tenant_id=TENANT_ID,
                tenant_key=TENANT_KEY,
            ))
        db.commit()
        return 1
    db.commit()
    return 0


def seed(do_build: bool = True) -> dict:
    """Fill BicycleCo gaps and (optionally) rebuild the graph."""
    db = SessionLocal()
    try:
        counts = {
            "cad": _ensure_cad(db),
            "aml": _ensure_aml(db),
            "avl": _ensure_avl(db),
            "documents": _ensure_documents(db),
            "costing": _ensure_cost_rows(db),
            "bom": _ensure_bom(db),
            "ecos": _ensure_ecos(db),
            "bike_eco": _ensure_bike_eco(db),
            "workflows": _ensure_workflows(db),
        }
        logger.info("BicycleCo enrichment counts: %s", counts)
    finally:
        db.close()

    graph = None
    if do_build:
        from db.indexing.build_graph import build
        graph = build(force=True)
        logger.info("Graph build result: %s", graph)
        db2 = SessionLocal()
        try:
            doc_edges = _ensure_doc_part_edges(db2)
            logger.info("Doc-part HAS_SPEC edges created: %d", doc_edges)
        finally:
            db2.close()
    return {"enriched": counts, "graph": graph}


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    no_build = "--no-build" in sys.argv
    logger.info("Seeding BicycleCo graph data (build=%s)", not no_build)
    result = seed(do_build=not no_build)
    counts = result["enriched"]
    logger.info("Done. Added per edge aspect: %s", counts)


if __name__ == "__main__":
    main()
