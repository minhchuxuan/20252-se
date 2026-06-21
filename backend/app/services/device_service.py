"""Device management & control service.

Implements the capability-driven control path (REQ-4.2.x) and the safety guards
(NFR-SAF). Manual user commands and rule-initiated commands both flow through
``apply_command`` so validation and safety rules are enforced uniformly.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..core.clock import now
from ..core.errors import NotFoundError, PermissionDeniedError, SafetyViolationError
from ..core.events import EventType, bus
from ..domain.capability import get_capability, validate_command
from ..domain.enums import CommandOutcome, DeviceType, Initiator, Role
from ..domain.models import Device, User
from ..adapters.devices import get_adapter
from ..repositories import DevicePermissionRepository, DeviceRepository
from ..schemas.device import CapabilityOut, CommandResult, DeviceCreate, MockProfileOut

# AC controls whose change implies a compressor on/off cycle (NFR-SAF-1).
_AC_COMPRESSOR_CONTROLS = {"power", "target", "mode"}


class DeviceService:
    def __init__(self, db: Session):
        self.db = db
        self.devices = DeviceRepository(db)
        self.permissions = DevicePermissionRepository(db)

    # ----------------------------------------------------------- queries
    def list_for_home(self, home_id: int) -> list[Device]:
        return self.devices.by_home(home_id)

    def get_or_404(self, device_id: int, home_id: int) -> Device:
        device = self.devices.in_home(device_id, home_id)
        if device is None:
            raise NotFoundError(f"Device {device_id} not found")
        return device

    def capability(self, device_id: int, home_id: int) -> CapabilityOut:
        device = self.get_or_404(device_id, home_id)
        schema = get_capability(DeviceType(device.type))
        return CapabilityOut(
            device_id=device.id,
            type=DeviceType(device.type),
            display_name=schema.display_name,
            telemetry=list(schema.telemetry),
            controls=[c.to_dict() for c in schema.controls],
            reversible=schema.reversible,
            safety_critical=device.safety_critical,
        )

    @staticmethod
    def mock_profiles() -> list[MockProfileOut]:
        from ..domain.capability import CAPABILITIES

        return [
            MockProfileOut(
                type=schema.type,
                display_name=schema.display_name,
                nominal_power_w=schema.nominal_power_w,
                telemetry=list(schema.telemetry),
                controls=[c.to_dict() for c in schema.controls],
            )
            for schema in CAPABILITIES.values()
        ]

    # ----------------------------------------------------------- mutations
    def add_mock_device(self, home_id: int, data: DeviceCreate) -> Device:
        """Add Mock Device use case."""
        # The Administrator (building owner) has no unit; devices are provisioned when a
        # unit is sold, so there is no unit to add an ad-hoc device to (least privilege).
        if home_id is None:
            raise PermissionDeniedError(
                "The administrator has no unit; devices are provisioned when a unit is sold"
            )
        schema = get_capability(data.type)
        adapter = get_adapter(data.type)
        device = Device(
            home_id=home_id,
            name=data.name,
            type=data.type,
            room=data.room,
            online=True,
            state=adapter.default_state(),
            kwh_total=0.0,
            safety_critical=data.safety_critical or schema.safety_critical_default,
            capability=schema.to_dict(),
            is_mock=True,
            last_seen_at=now(),
        )
        self.devices.add(device)
        self.db.commit()
        return device

    def delete_device(self, device_id: int, home_id: int) -> None:
        device = self.get_or_404(device_id, home_id)
        self.db.delete(device)
        self.db.commit()

    def set_connectivity(self, device_id: int, home_id: int, online: bool) -> Device:
        """Demo hook to force a device offline/online (exercises REQ-4.1.4)."""
        device = self.get_or_404(device_id, home_id)
        # NFR-SAF: a safety-critical device must always remain reachable so it keeps
        # reporting; it may not be forced offline.
        if device.safety_critical and not online:
            raise SafetyViolationError("A safety-critical device cannot be forced offline.")
        state = dict(device.state or {})
        state["forced_offline"] = not online
        device.state = state
        device.online = online
        if online:
            device.last_seen_at = now()
        self.db.commit()
        return device

    # ----------------------------------------------------------- control path
    def send_user_command(self, user: User, device_id: int, control: str, value: Any) -> CommandResult:
        # The Administrator (building owner) owns no unit and never operates devices —
        # reject by role before any home-scoped lookup (least privilege, NFR-SEC-2).
        if user.role == Role.ADMIN:
            raise PermissionDeniedError("The administrator cannot control devices")
        device = self.get_or_404(device_id, user.home_id)
        self._authorize_control(user, device)
        return self.apply_command(device, control, value, Initiator.USER)

    def apply_command(
        self, device: Device, control: str, value: Any, initiator: Initiator
    ) -> CommandResult:
        """Validate → safety-check → dispatch to adapter (REQ-4.2.3/4.2.4)."""
        # Offline device cannot accept commands within the 5s budget (REQ-4.2.4 timeout).
        if not device.online or (device.state or {}).get("forced_offline"):
            return CommandResult(
                outcome=CommandOutcome.TIMEOUT, device_id=device.id, control=control,
                value=value, detail="Device is unreachable",
            )

        result = validate_command(DeviceType(device.type), control, value)
        if not result.ok:
            return CommandResult(
                outcome=CommandOutcome.REJECTED, device_id=device.id, control=control,
                value=value, detail=result.error,
            )
        value = result.normalized

        safety = self._safety_check(device, control, value, initiator)
        if safety is not None:
            return safety

        adapter = get_adapter(DeviceType(device.type))
        new_state = adapter.apply_control(dict(device.state or {}), control, value)
        if DeviceType(device.type) == DeviceType.AC and control in _AC_COMPRESSOR_CONTROLS:
            new_state["last_ac_cmd_ts"] = now().isoformat()
        device.state = new_state
        device.last_seen_at = now()
        self.db.commit()

        bus.publish(
            EventType.COMMAND_APPLIED,
            {"device_id": device.id, "control": control, "value": value, "initiator": initiator.value},
        )
        return CommandResult(
            outcome=CommandOutcome.SUCCESS, device_id=device.id, control=control,
            value=value, state={k: v for k, v in new_state.items() if k != "last_ac_cmd_ts"},
        )

    # ----------------------------------------------------------- guards
    def _authorize_control(self, user: User, device: Device) -> None:
        # The Administrator (apartment owner) views only and never operates devices;
        # the Developer is the maintainer/diagnostics role; a Resident may operate
        # only devices explicitly granted to them (least privilege, NFR-SEC-2).
        if user.role == Role.DEVELOPER:
            return
        if user.role == Role.RESIDENT and self.permissions.can_control(user.id, device.id):
            return
        raise PermissionDeniedError("You do not have permission to control this device")

    def _safety_check(
        self, device: Device, control: str, value: Any, initiator: Initiator
    ) -> CommandResult | None:
        # NFR-SAF-2: never auto power-off a safety-critical device.
        if (
            device.safety_critical
            and initiator in (Initiator.SCHEDULER, Initiator.SYSTEM)
            and control == "power"
            and str(value).lower() == "off"
        ):
            return CommandResult(
                outcome=CommandOutcome.SKIPPED, device_id=device.id, control=control, value=value,
                detail="Blocked: cannot auto power-off a safety-critical device (NFR-SAF-2)",
            )
        # NFR-SAF-1: <= 1 AC compressor command per 3 minutes.
        if DeviceType(device.type) == DeviceType.AC and control in _AC_COMPRESSOR_CONTROLS:
            last = (device.state or {}).get("last_ac_cmd_ts")
            if last:
                from datetime import datetime

                last_ts = datetime.fromisoformat(last)
                if (now() - last_ts) < timedelta(seconds=settings.ac_compressor_min_interval_seconds):
                    return CommandResult(
                        outcome=CommandOutcome.REJECTED, device_id=device.id, control=control,
                        value=value,
                        detail=(
                            "Blocked: AC compressor command rate limit "
                            f"({settings.ac_compressor_min_interval_seconds}s, NFR-SAF-1)"
                        ),
                    )
        return None
