"""Bill of Materials model."""

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class BomItem(Base):
    __tablename__ = "bom"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    number = Column("number", String, nullable=True)
    level = Column("level", Integer, nullable=False)
    part_number = Column("part_number", String, ForeignKey("parts.part_number"), nullable=False)
    part_revision = Column("part_revision", String)
    part_name = Column("part_name", String)
    qty = Column("qty", Integer, nullable=False, default=1)
    uom = Column("uom", String)
    parent_assembly = Column("parent_assembly", String, ForeignKey("parts.part_number"))
    material_notes = Column("material_notes", String)
    bom_type = Column("bom_type", String, nullable=False, default="DESIGN")
    created_by = Column("created_by", Integer, ForeignKey("users.user_id"))
    modified_by = Column("modified_by", Integer, ForeignKey("users.user_id"))
    created_date = Column("created_date", String)
    modified_date = Column("modified_date", String)
    tenant_id = Column("tenant_id", Integer, ForeignKey("tenants.tenant_id"))
    tenant_key = Column("tenant_key", String, nullable=False)

    part = relationship("Part", back_populates="bom_items", foreign_keys=[part_number])
    parent = relationship("Part", foreign_keys=[parent_assembly])
