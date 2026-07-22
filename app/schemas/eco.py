"""ECO schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class EcoOut(BaseModel):
    eco_number: str
    eco_title: str
    eco_description: Optional[str] = None
    eco_status: str = "DRAFT"
    part_number: str
    current_revision: Optional[str] = None
    new_revision: Optional[str] = None
    affected_bom_level: Optional[int] = None
    change_type: Optional[str] = None
    change_detail: Optional[str] = None
    change_drafter: Optional[int] = None
    change_approver: Optional[int] = None
    drafted_date: Optional[str] = None
    approved_date: Optional[str] = None
    implemented_date: Optional[str] = None
    new_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
