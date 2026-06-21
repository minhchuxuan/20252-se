"""Administrator (building owner) service — building-wide oversight across units.

The Administrator owns no unit and never operates devices; this service aggregates
the per-unit telemetry that already exists into a building roster + totals, reusing
the home-scoped TelemetryService (DRY) rather than duplicating its computation.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.errors import NotFoundError
from ..domain.enums import Role
from ..domain.models import Home, User
from ..repositories import HomeRepository, UserRepository
from ..schemas.admin import BuildingOverview, UnitOverview
from .tariff_service import TariffService
from .telemetry_service import TelemetryService


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.homes = HomeRepository(db)
        self.users = UserRepository(db)
        self.telemetry = TelemetryService(db)
        self.tariffs = TariffService(db)

    def unit_or_404(self, home_id: int) -> Home:
        home = self.db.get(Home, home_id)
        if home is None:
            raise NotFoundError(f"Unit {home_id} not found")
        return home

    def building_overview(self) -> BuildingOverview:
        units: list[UnitOverview] = []
        residents = 0
        for home in self.homes.list():
            occupant = next(iter(self.users.by_home(home.id)), None)
            # The building overview counts only resident households; the Developer's
            # maintenance unit is internal and must not inflate the building totals.
            if occupant is None or occupant.role != Role.RESIDENT:
                continue
            residents += 1
            dash = self.telemetry.dashboard(home.id)
            units.append(UnitOverview(
                home_id=home.id, unit_name=home.name,
                resident_name=occupant.full_name if occupant else None,
                resident_email=occupant.email if occupant else None,
                total_w=dash.home_total_w, kwh_cycle=dash.kwh_cycle,
                estimated_bill_vnd=dash.estimated_bill_vnd,
                online_devices=dash.online_devices, total_devices=dash.total_devices,
            ))
        tariff = self.tariffs.active(None)
        return BuildingOverview(
            unit_count=len(units), resident_count=residents,
            total_w=round(sum(u.total_w for u in units), 1),
            kwh_cycle=round(sum(u.kwh_cycle for u in units), 3),
            estimated_bill_vnd=round(sum(u.estimated_bill_vnd for u in units), 0),
            currency=tariff.currency, units=units,
        )
