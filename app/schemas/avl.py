"""AVL schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class AvlOut(BaseModel):
    id: int
    part_number: str
    part_revision: Optional[str] = None
    part_name: Optional[str] = None
    vendor_name: str
    vendor_site: Optional[str] = None
    vendor_contact: Optional[str] = None
    vendor_part_number: Optional[str] = None
    vendor_status: Optional[str] = "APPROVED"
    preferred_flag: str = "No"
    lead_time_days: Optional[int] = None
    unit_price: Optional[float] = None
    currency: Optional[str] = "USD"
    min_order_qty: Optional[int] = 1
    moq_uom: Optional[str] = None
    payment_terms: Optional[str] = None
    shipping_method: Optional[str] = None
    contract_number: Optional[str] = None
    iso_certified: Optional[str] = None
    compliance_status: Optional[str] = None
    approval_date: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
