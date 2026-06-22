"""Administrator (building owner) service — building-wide oversight across units.

The Administrator owns no unit and never operates devices; this service aggregates
the per-unit telemetry that already exists into a building roster + totals, reusing
the home-scoped TelemetryService (DRY) rather than duplicating its computation.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..core.errors import ConflictError, NotFoundError
from ..domain.enums import Role
from ..domain.models import Home, User
from ..repositories import DevicePermissionRepository, HomeRepository, UserRepository
from ..schemas.admin import BuildingOverview, UnitOverview
from .tariff_service import TariffService
from .telemetry_service import TelemetryService


class AdminService:
    def __init__(self, db: Session):
        self.db = db
        self.homes = HomeRepository(db)
        self.users = UserRepository(db)
        self.permissions = DevicePermissionRepository(db)
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
            # The Developer's maintenance unit is internal infrastructure, not part of the
            # building's sellable inventory, so it is excluded from the owner's overview.
            if occupant is not None and occupant.role == Role.DEVELOPER:
                continue
            # Resident-occupied and vacant units are both the owner's inventory; a vacant
            # unit (e.g. after offboarding) is shown with no occupant and no household data.
            is_resident = occupant is not None and occupant.role == Role.RESIDENT
            if is_resident:
                residents += 1
            dash = self.telemetry.dashboard(home.id)
            units.append(UnitOverview(
                home_id=home.id, unit_name=home.name,
                resident_name=occupant.full_name if is_resident else None,
                resident_email=occupant.email if is_resident else None,
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

    def offboard_resident(self, home_id: int) -> None:
        """Remove the Resident from a unit (the lifecycle counterpart to selling it).

        This is a *soft* offboard: the account is deactivated (NFR-SEC-2: disabled accounts
        cannot authenticate) and detached from the unit, which becomes vacant. The unit, its
        devices and all telemetry/billing history are deliberately retained for resale and
        audit; only the resident's access (account + device-control grants) is revoked.
        """
        self.unit_or_404(home_id)
        resident = next(
            (u for u in self.users.by_home(home_id) if u.role == Role.RESIDENT), None
        )
        if resident is None:
            raise ConflictError("This unit has no resident to remove")
        for grant in self.permissions.for_user(resident.id):
            self.permissions.delete(grant)
        resident.is_active = False
        resident.home_id = None
        self.db.commit()
