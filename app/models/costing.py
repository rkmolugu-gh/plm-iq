"""Costing BOM model."""

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class CostingBomItem(Base):
    __tablename__ = "costing_bom"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    level = Column("level", Integer, nullable=False)
    part_number = Column("part_number", String, ForeignKey("parts.part_number"), nullable=False)
    part_name = Column("part_name", String)
    qty = Column("qty", Integer, nullable=False, default=1)
    uom = Column("uom", String)
    material_cost = Column("material_cost", Numeric(12, 4), nullable=False, default=0)
    labor_cost = Column("labor_cost", Numeric(12, 4), nullable=False, default=0)
    overhead_cost = Column("overhead_cost", Numeric(12, 4), nullable=False, default=0)
    machining_cost = Column("machining_cost", Numeric(12, 4), nullable=False, default=0)
    unit_cost = Column("unit_cost", Numeric(12, 4), nullable=False, default=0)
    extended_cost = Column("extended_cost", Numeric(12, 4), nullable=False, default=0)
    rolled_total = Column("rolled_total", Numeric(12, 4), nullable=False, default=0)
    cost_type = Column("cost_type", String, nullable=False)
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    modified_by = Column("modified_by", Integer, ForeignKey("users.user_id"))
    created_date = Column("created_date", String)
    modified_date = Column("modified_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"))
    tenant_key = Column("tenant_key", String, nullable=False)
    node_id = Column("node_id", Integer, ForeignKey("plmiq_node.node_id"))

    node = relationship("GraphNode")

    part = relationship("Part", back_populates="costing_items")
