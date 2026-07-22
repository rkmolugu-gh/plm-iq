"""Costing schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class CostingItemOut(BaseModel):
    id: int
    level: int
    part_number: str
    part_name: Optional[str] = None
    qty: int = 1
    uom: Optional[str] = None
    material_cost: float = 0
    labor_cost: float = 0
    overhead_cost: float = 0
    machining_cost: float = 0
    unit_cost: float = 0
    extended_cost: float = 0
    rolled_total: float = 0
    cost_type: str

    model_config = ConfigDict(from_attributes=True)
