"""AML schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class AmlOut(BaseModel):
    id: int
    part_number: str
    part_revision: Optional[str] = None
    part_name: Optional[str] = None
    manufacturer_name: str
    manufacturer_part_number: Optional[str] = None
    manufacturer_status: Optional[str] = "APPROVED"
    source_type: str
    preferred_flag: str = "No"
    lead_time_days: Optional[int] = None
    unit_cost: Optional[float] = None
    currency: Optional[str] = "USD"
    compliance_status: Optional[str] = None
    quality_rating: Optional[str] = None
    approval_date: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
