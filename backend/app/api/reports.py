"""Report & CSV export endpoints (Other Requirements 6.1)."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..core.clock import now
from ..database import get_db
from ..domain.models import User
from ..services.report_service import ReportService
from .deps import get_current_user


def _csv_response(text: str, filename: str) -> Response:
    return Response(
        content=text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/export/readings.csv")
def export_readings(
    days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    end = now()
    start = end - timedelta(days=days)
    return _csv_response(ReportService(db).export_readings_csv(user.home_id, start, end), "readings.csv")


@router.get("/export/rules.csv")
def export_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _csv_response(ReportService(db).export_rules_csv(user.home_id), "rules.csv")


@router.get("/export/savings.csv")
def export_savings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _csv_response(ReportService(db).export_savings_csv(user.home_id), "savings.csv")
