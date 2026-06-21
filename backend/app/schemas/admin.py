"""Administrator (building owner) DTOs — the building-wide oversight views."""
from __future__ import annotations

from pydantic import BaseModel


class UnitOverview(BaseModel):
    home_id: int
    unit_name: str
    resident_name: str | None
    resident_email: str | None
    total_w: float
    kwh_cycle: float
    estimated_bill_vnd: float
    online_devices: int
    total_devices: int


class BuildingOverview(BaseModel):
    unit_count: int
    resident_count: int
    total_w: float
    kwh_cycle: float
    estimated_bill_vnd: float
    currency: str
    units: list[UnitOverview]
