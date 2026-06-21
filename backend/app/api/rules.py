"""Rule / scheduling / auto-action endpoints (REQ-4.3.x)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.models import Rule, User
from ..schemas.rule import (
    RuleCreate,
    RuleExecutionOut,
    RuleOut,
    RuleUpdate,
    RuleValidationOut,
)
from ..services.device_service import DeviceService
from ..services.rule_engine import RuleEngine
from .deps import get_current_user

router = APIRouter(prefix="/api", tags=["rules"])


def _to_out(engine: RuleEngine, rule: Rule) -> RuleOut:
    out = RuleOut.model_validate(rule)
    device = engine.devices.get(rule.device_id)
    out.summary = engine.summarize(device, rule.when_json, rule.then_json, rule.until_json)
    return out


@router.get("/rules", response_model=list[RuleOut])
def list_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    engine = RuleEngine(db)
    return [_to_out(engine, r) for r in engine.list_for_home(user.home_id)]


@router.post("/rules/validate", response_model=RuleValidationOut)
def validate_rule(
    body: RuleCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Pre-save check: conflicts (REQ-4.3.3), safety warnings (NFR-SAF-3),
    and VND saving estimate (REQ-4.5.3)."""
    engine = RuleEngine(db)
    return engine.validate(
        user.home_id,
        body.device_id,
        body.when_.model_dump(exclude_none=True),
        body.then.model_dump(),
        body.until.model_dump(exclude_none=True) if body.until else None,
    )


@router.post("/rules", response_model=RuleOut, status_code=201)
def create_rule(
    body: RuleCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    engine = RuleEngine(db)
    rule = engine.create(user.home_id, user.id, body)
    return _to_out(engine, rule)


@router.get("/rules/{rule_id}", response_model=RuleOut)
def get_rule(rule_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    engine = RuleEngine(db)
    return _to_out(engine, engine.get_or_404(rule_id, user.home_id))


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: int,
    body: RuleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    engine = RuleEngine(db)
    return _to_out(engine, engine.update(rule_id, user.home_id, body))


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    RuleEngine(db).delete(rule_id, user.home_id)


@router.get("/rules/{rule_id}/executions", response_model=list[RuleExecutionOut])
def rule_executions(
    rule_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return RuleEngine(db).executions(rule_id, user.home_id)


@router.post("/executions/{execution_id}/undo", response_model=RuleExecutionOut)
def undo_execution(
    execution_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """REQ-4.3.6: undo an auto-action within 2 minutes."""
    return RuleEngine(db).undo(execution_id, user.home_id)
