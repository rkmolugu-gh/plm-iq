"""Part schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class PartOut(BaseModel):
    part_number: str
    part_revision: str
    part_name: str
    spec_file: Optional[str] = None
    material: Optional[str] = None
    uom: str
    qty: int = 1
    status: str = "DRAFT"
    created_date: Optional[str] = None
    modified_date: Optional[str] = None
    modified_owner: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class PartDetail(PartOut):
    """Full part detail with related entity links."""
    bom_count: int = 0
    costing_count: int = 0
    eco_count: int = 0
    aml_count: int = 0
    avl_count: int = 0
    cad_count: int = 0
