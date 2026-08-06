"""Engineering Change Order model."""

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class EngineeringChangeOrder(Base):
    __tablename__ = "engineering_change_orders"

    eco_number = Column("eco_number", String, primary_key=True)
    eco_title = Column("eco_title", String, nullable=False)
    eco_description = Column("eco_description", String)
    eco_status = Column("eco_status", String, nullable=False, default="DRAFT")
    part_number = Column("part_number", String, ForeignKey("parts.part_number"), nullable=False)
    current_revision = Column("current_revision", String)
    new_revision = Column("new_revision", String)
    affected_bom_level = Column("affected_bom_level", Integer)
    change_type = Column("change_type", String)
    change_detail = Column("change_detail", String)
    change_drafter = Column("change_drafter", Integer, ForeignKey("users.user_id"))
    change_approver = Column("change_approver", Integer, ForeignKey("users.user_id"))
    drafted_date = Column("drafted_date", String)
    approved_date = Column("approved_date", String)
    implemented_date = Column("implemented_date", String)
    new_status = Column("new_status", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)

    part = relationship("Part", back_populates="eco_items")
