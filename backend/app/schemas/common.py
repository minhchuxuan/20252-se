"""Shared DTO primitives."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class Message(BaseModel):
    message: str


class Action(BaseModel):
    """THEN clause of a rule — a single control change."""
    control: str
    value: Any


class Condition(BaseModel):
    """WHEN/UNTIL clause. ``type`` selects which fields apply; the rule engine
    validates the combination and produces human-readable errors.

    Supported types:
      * time          — at:"HH:MM"  OR  between:["HH:MM","HH:MM"]
      * day           — days:["mon",...,"sun"]
      * occupancy     — device_id, value:bool, for_minutes:int (sensor empty/occupied)
      * device_state  — device_id, control, op:"eq|ne|gt|lt", value
      * tariff_window — window:"peak|offpeak|normal"
    """
    type: str
    at: str | None = None
    between: list[str] | None = None
    days: list[str] | None = None
    device_id: int | None = None
    channel: str | None = None
    control: str | None = None
    op: str | None = None
    value: Any = None
    for_minutes: int | None = None
    window: str | None = None
