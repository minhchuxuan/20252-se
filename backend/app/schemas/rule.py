"""Rule / scheduling / execution DTOs (REQ-4.3.x)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..domain.enums import CommandOutcome, Initiator, RuleSource
from .common import Action, Condition


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    device_id: int
    when_: Condition = Field(alias="when")
    then: Action
    until: Condition | None = None
    enabled: bool = True
    auto_apply: bool = False   # REQ-4.3.6: off by default
    priority: int = 100

    model_config = ConfigDict(populate_by_name=True)


class RuleUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    auto_apply: bool | None = None
    priority: int | None = None
    when_: Condition | None = Field(default=None, alias="when")
    then: Action | None = None
    until: Condition | None = None

    model_config = ConfigDict(populate_by_name=True)


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    device_id: int
    enabled: bool
    auto_apply: bool
    priority: int
    when_json: dict[str, Any]
    then_json: dict[str, Any]
    until_json: dict[str, Any] | None
    source: RuleSource
    estimated_monthly_saving_vnd: float
    needs_recalculation: bool
    created_at: datetime
    summary: str | None = None    # human-readable "WHEN ... THEN ..."


class ConflictItem(BaseModel):
    rule_id: int
    rule_name: str
    reason: str


class RuleValidationOut(BaseModel):
    """Returned before saving (REQ-4.3.3 conflict, REQ-4.5.3 estimate, NFR-SAF warnings)."""
    valid: bool
    errors: list[str] = []
    conflicts: list[ConflictItem] = []
    warnings: list[str] = []
    estimated_monthly_saving_vnd: float = 0.0
    summary: str = ""


class RuleExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_id: int
    device_id: int
    ts: datetime
    action_json: dict[str, Any]
    initiator: Initiator
    outcome: CommandOutcome
    detail: str | None
    undo_deadline: datetime | None
    undone: bool
