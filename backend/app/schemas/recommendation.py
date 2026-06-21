"""Habit/recommendation DTOs (REQ-4.4.x)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..domain.enums import RecommendationStatus


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    title: str
    when_json: dict[str, Any]
    then_json: dict[str, Any]
    until_json: dict[str, Any] | None
    rationale: str
    data_window_start: datetime
    data_window_end: datetime
    estimated_monthly_saving_vnd: float
    status: RecommendationStatus
    summary: str | None = None


class AcceptRecommendation(BaseModel):
    """Optional edits applied when accepting (REQ-4.4: user may edit)."""
    name: str | None = None
    auto_apply: bool = False
