"""Graph layer models (plmiq prefix) — relationship/traceability layer over domain tables.

plmiq_node is a NODE IDENTITY registry only — no type is stored on the node.
The type of a node is derived from the business object that owns it: every
node-capable domain table carries a UNIQUE nullable node_id FK to plmiq_node
(parts, costing_bom, engineering_change_orders, AML, AVL, cad_metadata,
documents, workflow_definitions/instances/tasks, users, tenants). This avoids
duplicating object type on the node. Edges relate nodes; annotations, evidence
and impact are supplementary layers on edges.

See docs/plm-iq-graph-concepts.txt for the conceptual model and phase plan.
"""

from sqlalchemy import Boolean, Column, Integer, Numeric, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class GraphNode(Base):
    """A graph node identity; the owning business object supplies the node's type."""

    __tablename__ = "plmiq_node"

    node_id = Column("node_id", Integer, primary_key=True, autoincrement=True)
    node_label = Column("node_label", String)
    attributes = Column("attributes", String)  # JSON
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    created_date = Column("created_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)


class GraphEdgeType(Base):
    """Governed catalog of semantic edge types (canonical direction + inverse type)."""

    __tablename__ = "plmiq_edge_type"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    name = Column("name", String, nullable=False, unique=True)
    description = Column("description", String)
    canonical_direction = Column("canonical_direction", String)
    inverse_type = Column("inverse_type", String)
    is_active = Column("is_active", Boolean, nullable=False, default=True)
    created_date = Column("created_date", String)
    tenant_key = Column("tenant_key", String, nullable=False, default="plm-iq")


class GraphEdge(Base):
    """A directed, typed edge between two nodes."""

    __tablename__ = "plmiq_edge"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    source_node_id = Column("source_node_id", Integer, ForeignKey("plmiq_node.node_id"), nullable=False)
    target_node_id = Column("target_node_id", Integer, ForeignKey("plmiq_node.node_id"), nullable=False)
    edge_type_id = Column("edge_type_id", Integer, ForeignKey("plmiq_edge_type.id"), nullable=False)
    state = Column("state", String)
    quantity = Column("quantity", Numeric(12, 4))
    unit = Column("unit", String)
    sequence = Column("sequence", Integer)
    attributes = Column("attributes", String)  # JSON (edge properties extension)
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    updated_by = Column("updated_by", Integer, ForeignKey("users.user_id"))
    created_date = Column("created_date", String)
    updated_date = Column("updated_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)

    source_node = relationship("GraphNode", foreign_keys=[source_node_id])
    target_node = relationship("GraphNode", foreign_keys=[target_node_id])
    edge_type = relationship("GraphEdgeType")


class GraphEdgeAnnotation(Base):
    """Commentary attached to an edge (why the relationship matters)."""

    __tablename__ = "plmiq_edge_annotation"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    edge_id = Column("edge_id", Integer, ForeignKey("plmiq_edge.id"), nullable=False)
    annotation_type = Column("annotation_type", String, nullable=False, default="GENERAL")
    text = Column("text", String, nullable=False)
    author_type = Column("author_type", String, nullable=False, default="human")  # human | ai
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    created_date = Column("created_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)

    edge = relationship("GraphEdge")


class GraphEdgeEvidence(Base):
    """Source supporting an edge or AI conclusion (why we believe it)."""

    __tablename__ = "plmiq_edge_evidence"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    edge_id = Column("edge_id", Integer, ForeignKey("plmiq_edge.id"), nullable=False)
    evidence_type = Column("evidence_type", String, nullable=False)  # BOM_RECORD | SOURCE_OBJECT | ...
    reference = Column("reference", String)
    confidence = Column("confidence", Numeric(6, 4))
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    created_date = Column("created_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)

    edge = relationship("GraphEdge")


class GraphEdgeImpact(Base):
    """Assessed effect of a change, expressed on an edge."""

    __tablename__ = "plmiq_edge_impact"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    edge_id = Column("edge_id", Integer, ForeignKey("plmiq_edge.id"), nullable=False)
    impact_type = Column("impact_type", String, nullable=False)  # DIRECT | DOWNSTREAM | UPSTREAM | ...
    impact_level = Column("impact_level", String)
    confidence = Column("confidence", Numeric(6, 4))
    reason = Column("reason", String)
    analysis_method = Column("analysis_method", String)
    evidence_count = Column("evidence_count", Integer, default=0)
    reviewed = Column("reviewed", Boolean, nullable=False, default=False)
    review_decision = Column("review_decision", String)
    analysis_run_id = Column("analysis_run_id", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)

    edge = relationship("GraphEdge")
