"""Monitoring / dashboard DTOs (REQ-4.1.x)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DeviceLive(BaseModel):
    device_id: int
    name: str
    type: str
    room: str
    online: bool
    power_w: float
    kwh_today: float
    temperature: float | None = None
    occupancy: bool | None = None


class DashboardOut(BaseModel):
    home_total_w: float                # instantaneous home power
    kwh_today: float
    kwh_cycle: float                   # current billing cycle
    estimated_bill_vnd: float          # projected for cycle
    savings_cycle_vnd: float           # REQ-4.5.4 savings so far this cycle
    currency: str
    tariff_name: str
    online_devices: int
    total_devices: int
    devices: list[DeviceLive]
    generated_at: datetime


class ConsumptionPoint(BaseModel):
    bucket: str        # ISO date or datetime label
    kwh: float
    cost_vnd: float


class TopConsumer(BaseModel):
    device_id: int
    name: str
    type: str
    kwh: float
    cost_vnd: float
    share_pct: float


class ConsumptionSeries(BaseModel):
    device_id: int | None
    granularity: str           # "hour" | "day"
    start: datetime
    end: datetime
    points: list[ConsumptionPoint]
    total_kwh: float
    total_cost_vnd: float
