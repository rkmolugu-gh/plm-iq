"""Approved Manufacturer List model."""

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ApprovedManufacturer(Base):
    __tablename__ = "approved_manufacturer_list"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    part_number = Column("part_number", String, ForeignKey("parts.part_number"), nullable=False)
    part_revision = Column("part_revision", String)
    part_name = Column("part_name", String)
    manufacturer_name = Column("manufacturer_name", String, nullable=False)
    manufacturer_part_number = Column("manufacturer_part_number", String)
    manufacturer_status = Column("manufacturer_status", String, default="APPROVED")
    source_type = Column("source_type", String, nullable=False)
    preferred_flag = Column("preferred_flag", String, nullable=False, default="No")
    lead_time_days = Column("lead_time_days", Integer)
    unit_cost = Column("unit_cost", Numeric(12, 4))
    currency = Column("currency", String, default="USD")
    compliance_status = Column("compliance_status", String)
    quality_rating = Column("quality_rating", String)
    approval_date = Column("approval_date", String)
    notes = Column("notes", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)
    tenant_key = Column("tenant_key", String, nullable=False)

    part = relationship("Part", back_populates="aml_items")
