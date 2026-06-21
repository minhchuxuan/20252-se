"""Habit recommendation endpoints (REQ-4.4.x)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.models import Recommendation, User
from ..schemas.recommendation import AcceptRecommendation, RecommendationOut
from ..schemas.rule import RuleOut
from ..services.recommendation_service import RecommendationService
from ..services.rule_engine import RuleEngine
from .deps import get_current_user

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _to_out(svc: RecommendationService, rec: Recommendation) -> RecommendationOut:
    out = RecommendationOut.model_validate(rec)
    device = svc.devices.get(rec.device_id)
    out.summary = RuleEngine(svc.db).summarize(device, rec.when_json, rec.then_json, rec.until_json)
    return out


@router.get("", response_model=list[RecommendationOut])
def list_recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = RecommendationService(db)
    return [_to_out(svc, r) for r in svc.list_active(user.home_id)]


@router.post("/analyze", response_model=list[RecommendationOut])
def analyze(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run the habit miner now (REQ-4.4.1: needs >= 7 days of telemetry)."""
    svc = RecommendationService(db)
    return [_to_out(svc, r) for r in svc.analyze(user.home_id)]


@router.post("/{rec_id}/accept", response_model=RuleOut, status_code=201)
def accept(
    rec_id: int,
    body: AcceptRecommendation,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """REQ-4.4.4: explicit acceptance turns the recommendation into a rule."""
    svc = RecommendationService(db)
    rule = svc.accept(rec_id, user.home_id, body.name, body.auto_apply)
    engine = RuleEngine(db)
    out = RuleOut.model_validate(rule)
    out.summary = engine.summarize(engine.devices.get(rule.device_id), rule.when_json, rule.then_json, rule.until_json)
    return out


@router.post("/{rec_id}/dismiss", response_model=RecommendationOut)
def dismiss(rec_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """REQ-4.4.5: dismissed for the same device/condition for >= 30 days."""
    svc = RecommendationService(db)
    return _to_out(svc, svc.dismiss(rec_id, user.home_id))
