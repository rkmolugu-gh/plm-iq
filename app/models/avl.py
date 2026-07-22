"""Approved Vendor List model."""

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class ApprovedVendor(Base):
    __tablename__ = "approved_vendor_list"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    part_number = Column("part_number", String, ForeignKey("parts.part_number"), nullable=False)
    part_revision = Column("part_revision", String)
    part_name = Column("part_name", String)
    vendor_name = Column("vendor_name", String, nullable=False)
    vendor_site = Column("vendor_site", String)
    vendor_contact = Column("vendor_contact", String)
    vendor_part_number = Column("vendor_part_number", String)
    vendor_status = Column("vendor_status", String, default="APPROVED")
    preferred_flag = Column("preferred_flag", String, nullable=False, default="No")
    lead_time_days = Column("lead_time_days", Integer)
    unit_price = Column("unit_price", Numeric(12, 4))
    currency = Column("currency", String, default="USD")
    min_order_qty = Column("min_order_qty", Integer, default=1)
    moq_uom = Column("moq_uom", String)
    payment_terms = Column("payment_terms", String)
    shipping_method = Column("shipping_method", String)
    contract_number = Column("contract_number", String)
    iso_certified = Column("iso_certified", String)
    compliance_status = Column("compliance_status", String)
    approval_date = Column("approval_date", String)
    notes = Column("notes", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"), nullable=False, default=1)

    part = relationship("Part", back_populates="avl_items")
