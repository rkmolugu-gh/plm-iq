"""BOM schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class BomItemOut(BaseModel):
    id: int
    level: int
    part_number: str
    part_revision: Optional[str] = None
    part_name: Optional[str] = None
    qty: int = 1
    uom: Optional[str] = None
    parent_assembly: Optional[str] = None
    material_notes: Optional[str] = None
    bom_type: str = "DESIGN"

    model_config = ConfigDict(from_attributes=True)


class BomTree(BaseModel):
    """Tree node for hierarchical BOM display."""
    item: BomItemOut
    children: list["BomTree"] = []

    model_config = ConfigDict(from_attributes=True)
