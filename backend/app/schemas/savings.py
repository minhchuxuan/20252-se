"""Optimization / bill-saving DTOs (REQ-4.5.x)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..domain.enums import SavingsKind


class SavingsEstimate(BaseModel):
    """Shown before a rule/recommendation is saved (REQ-4.5.3).

    saved_vnd = sum((baseline_kWh - expected_kWh_with_rule) * tariff_VND_per_kWh)
    """
    baseline_kwh_month: float
    expected_kwh_month: float
    saved_kwh_month: float
    saved_vnd_month: float
    tariff_vnd_per_kwh: float
    explanation: str


class SavingsSummary(BaseModel):
    """Dashboard / reports rollup (REQ-4.5.4)."""
    cycle_start: datetime
    cycle_end: datetime
    saved_kwh_cycle: float
    saved_vnd_cycle: float
    estimated_saved_vnd_month: float
    currency: str


class SavingsRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_id: int | None
    device_id: int
    period_start: datetime
    period_end: datetime
    baseline_kwh: float
    expected_kwh_with_rule: float
    actual_kwh: float | None
    saved_kwh: float
    saved_vnd: float
    kind: SavingsKind
