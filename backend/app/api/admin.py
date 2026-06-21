"""Administrator (building owner) endpoints — building-wide oversight (NFR-SEC-2).

These are the only views that span more than one unit, and they are read-only: the
Administrator monitors every unit and manages the building tariff/residents, but
never operates a resident's devices (least privilege)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain.models import User
from ..schemas.admin import BuildingOverview
from ..schemas.device import DeviceOut
from ..schemas.telemetry import DashboardOut
from ..services.admin_service import AdminService
from ..services.device_service import DeviceService
from ..services.telemetry_service import TelemetryService
from .deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview", response_model=BuildingOverview)
def building_overview(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Roster + per-unit power/bill + building totals for the building owner."""
    return AdminService(db).building_overview()


@router.get("/units/{home_id}/dashboard", response_model=DashboardOut)
def unit_dashboard(home_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """View a single unit's dashboard (read-only drill-in)."""
    AdminService(db).unit_or_404(home_id)
    return TelemetryService(db).dashboard(home_id)


@router.get("/units/{home_id}/devices", response_model=list[DeviceOut])
def unit_devices(home_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """View a single unit's devices (read-only drill-in)."""
    AdminService(db).unit_or_404(home_id)
    return DeviceService(db).list_for_home(home_id)
