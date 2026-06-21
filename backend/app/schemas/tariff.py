"""Tariff / settings DTOs."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..domain.enums import TariffType


class TariffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: TariffType = TariffType.FLAT
    config: dict[str, Any] = Field(default_factory=dict)
    currency: str = "VND"


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: TariffType
    config: dict[str, Any]
    currency: str
    active: bool


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    title: str
    body: str
    data: dict[str, Any]
    read: bool
    ts: Any


class SettingsOut(BaseModel):
    home_id: int | None  # NULL for the Administrator (building-wide, no single unit)
    home_name: str
    locale: str
    currency: str
    billing_cycle_day: int
    active_tariff: TariffOut | None
