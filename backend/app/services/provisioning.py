"""Unit provisioning.

When the Administrator (building owner) sells a unit to a Resident it ships with a
standard package of smart devices. This module is the single source of truth for
that package, reused by both the demo seed and live onboarding (DRY / SRP).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..adapters.devices import get_adapter
from ..domain.capability import get_capability
from ..domain.enums import DeviceType
from ..domain.models import Device, DevicePermission, Home, User

# (name, room, type, safety_critical) — the package every unit comes with.
DEFAULT_UNIT_DEVICES: list[tuple[str, str, DeviceType, bool]] = [
    ("Living Room TV Plug", "Living room", DeviceType.PLUG, False),
    ("Hallway Light", "Hallway", DeviceType.BULB, False),
    ("Bedroom AC", "Bedroom", DeviceType.AC, False),
    ("Living Room Fan", "Living room", DeviceType.FAN, False),
    ("Kitchen Fridge Plug", "Kitchen", DeviceType.PLUG, True),
    ("Living Room Sensor", "Living room", DeviceType.SENSOR, False),
]


def provision_unit(db: Session, home: Home, resident: User | None) -> dict[str, Device]:
    """Create the default device package in ``home`` and grant the Resident control
    of every operable device. The safety-critical fridge is monitored, never switched,
    and the sensor is read-only, so neither is granted (NFR-SAF-2 / least privilege)."""
    devices: dict[str, Device] = {}
    for name, room, dtype, safety in DEFAULT_UNIT_DEVICES:
        schema = get_capability(dtype)
        adapter = get_adapter(dtype)
        device = Device(
            home_id=home.id, name=name, type=dtype, room=room, online=True,
            state=adapter.default_state(), kwh_total=0.0, safety_critical=safety,
            capability=schema.to_dict(), is_mock=True,
        )
        db.add(device)
        db.flush()
        devices[name] = device
        operable = dtype != DeviceType.SENSOR and not safety
        if resident is not None and operable:
            db.add(DevicePermission(user_id=resident.id, device_id=device.id, can_control=True))
    return devices
