"""Optimization / bill-saving endpoints (REQ-4.5.x)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.models import User
from ..schemas.rule import RuleCreate
from ..schemas.savings import SavingsEstimate, SavingsRecordOut, SavingsSummary
from ..services.device_service import DeviceService
from ..services.optimization_service import OptimizationService
from .deps import get_current_user

router = APIRouter(prefix="/api/savings", tags=["savings"])


@router.get("/summary", response_model=SavingsSummary)
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """REQ-4.5.4: savings so far in the current billing cycle."""
    return OptimizationService(db).savings_summary(user.home_id)


@router.get("/records", response_model=list[SavingsRecordOut])
def records(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return OptimizationService(db).savings.by_home(user.home_id)


@router.post("/estimate", response_model=SavingsEstimate)
def estimate(
    body: RuleCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """REQ-4.5.3: estimate monthly saving BEFORE the rule is saved."""
    device = DeviceService(db).get_or_404(body.device_id, user.home_id)
    return OptimizationService(db).estimate_rule(
        device,
        body.when_.model_dump(exclude_none=True),
        body.then.model_dump(),
        body.until.model_dump(exclude_none=True) if body.until else None,
    )
