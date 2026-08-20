"""Part model."""

from sqlalchemy import Boolean, Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Part(Base):
    __tablename__ = "parts"

    part_id = Column("part_id", Integer, primary_key=True, autoincrement=True)
    part_number = Column("part_number", String, nullable=False)
    part_revision = Column("part_revision", String, nullable=False)
    part_name = Column("part_name", String, nullable=False)
    spec_file = Column("spec_file", String)
    material = Column("material", String)
    uom = Column("uom", String, nullable=False)
    qty = Column("qty", Integer, nullable=False, default=1)
    status = Column("status", String, nullable=False, default="DRAFT")
    in_workflow = Column("in_workflow", Boolean, nullable=False, default=False)
    active_workflow_instance_id = Column("active_workflow_instance_id", Integer, ForeignKey("workflow_instances.id"))
    created_date = Column("created_date", String)
    modified_date = Column("modified_date", String)
    modified_owner = Column("modified_owner", Integer, ForeignKey("users.user_id"))
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    tenant = relationship("Tenant", back_populates="parts")
    bom_items = relationship("BomItem", back_populates="part", foreign_keys="BomItem.part_id")
    costing_items = relationship("CostingBomItem", back_populates="part")
    eco_items = relationship("EngineeringChangeOrder", back_populates="part")
    aml_items = relationship("ApprovedManufacturer", back_populates="part")
    avl_items = relationship("ApprovedVendor", back_populates="part")
    cad_files = relationship("CadMetadata", back_populates="part")
