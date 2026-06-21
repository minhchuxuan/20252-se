"""Real-time monitoring & consumption endpoints (REQ-4.1.x)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.clock import now
from ..core.timeutil import current_billing_cycle, start_of_day
from ..database import get_db
from ..domain.models import Home, User
from ..schemas.telemetry import ConsumptionSeries, DashboardOut, TopConsumer
from ..services.telemetry_service import TelemetryService
from .deps import get_current_user

router = APIRouter(prefix="/api", tags=["monitoring"])


def _range(user_home_id: int, db: Session, range_key: str) -> tuple:
    ts = now()
    if range_key == "today":
        return start_of_day(ts), ts, "hour"
    if range_key == "week":
        return ts - timedelta(days=7), ts, "day"
    home = db.get(Home, user_home_id)
    start, _ = current_billing_cycle(ts, home.billing_cycle_day if home else 1)
    return start, ts, "day"


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return TelemetryService(db).dashboard(user.home_id)


@router.get("/consumption", response_model=ConsumptionSeries)
def consumption(
    device_id: int | None = Query(default=None),
    range_key: str = Query(default="today", alias="range"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end, gran = _range(user.home_id, db, range_key)
    return TelemetryService(db).consumption_series(user.home_id, device_id, start, end, gran)


@router.get("/top-consumers", response_model=list[TopConsumer])
def top_consumers(
    range_key: str = Query(default="today", alias="range"),
    limit: int = Query(default=3, ge=1, le=10),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start, end, _ = _range(user.home_id, db, range_key)
    return TelemetryService(db).top_consumers(user.home_id, start, end, limit)
