"""Device, capability and command DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..domain.enums import CommandOutcome, DeviceType


class MockProfileOut(BaseModel):
    """A selectable mock-device profile (Add Mock Device use case)."""
    type: DeviceType
    display_name: str
    nominal_power_w: float
    telemetry: list[str]
    controls: list[dict[str, Any]]


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: DeviceType
    room: str = Field(default="Living room", max_length=80)
    safety_critical: bool = False


class CapabilityOut(BaseModel):
    """Response of GET /api/devices/{id}/capabilities (REQ-4.2.1)."""
    device_id: int
    type: DeviceType
    display_name: str
    telemetry: list[str]
    controls: list[dict[str, Any]]
    reversible: bool
    safety_critical: bool


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: DeviceType
    room: str
    online: bool
    last_seen_at: datetime
    state: dict[str, Any]
    kwh_total: float
    safety_critical: bool
    is_mock: bool


class CommandRequest(BaseModel):
    control: str
    value: Any


class CommandResult(BaseModel):
    """REQ-4.2.4: success | rejected | timeout."""
    outcome: CommandOutcome
    device_id: int
    control: str
    value: Any = None
    detail: str | None = None
    state: dict[str, Any] | None = None
