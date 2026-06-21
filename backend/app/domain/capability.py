"""Device capability schema (REQ-4.2.1).

The capability schema is the single source of truth that drives BOTH:

  * the frontend  -> it renders controls from the schema instead of hard-coding
                     one screen per device model (SRS 3.1, Quality: add a device
                     type by changing only the adapter + schema), and
  * the backend   -> it validates every command against the declared ranges /
                     value-sets before dispatching (REQ-4.2.3).

Schemas are declared as data (not code branches) and exposed verbatim through
``GET /api/devices/{id}/capabilities``. Adding a new device type = add one
``CapabilitySchema`` entry here + one adapter (Strategy) — nothing else.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .enums import ControlKind, DeviceType


@dataclass(frozen=True)
class Control:
    """One controllable feature of a device."""
    name: str
    label: str
    kind: ControlKind
    unit: str | None = None
    # RANGE controls:
    min: float | None = None
    max: float | None = None
    step: float | None = None
    # ENUM controls:
    values: tuple[str, ...] | None = None
    # Default value used when a mock device is created.
    default: Any = None
    # Safety flag (NFR-SAF-3): UI must warn before applying such a control.
    safety_sensitive: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        if self.values is not None:
            d["values"] = list(self.values)
        # Drop irrelevant keys to keep the schema payload clean per control kind.
        return {k: v for k, v in d.items() if v is not None}


@dataclass(frozen=True)
class CapabilitySchema:
    """Full capability description for a device type."""
    type: DeviceType
    display_name: str
    telemetry: tuple[str, ...]            # channels the device reports
    controls: tuple[Control, ...]          # controllable features ([] = read-only)
    reversible: bool = True                # supports undo of an applied command
    safety_critical_default: bool = False  # e.g. fridge/medical (NFR-SAF-2)
    nominal_power_w: float = 0.0           # typical draw when 'on', for the simulator

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "display_name": self.display_name,
            "telemetry": list(self.telemetry),
            "controls": [c.to_dict() for c in self.controls],
            "reversible": self.reversible,
            "safety_critical_default": self.safety_critical_default,
            "nominal_power_w": self.nominal_power_w,
        }

    def control(self, name: str) -> Control | None:
        for c in self.controls:
            if c.name == name:
                return c
        return None

    def control_names(self) -> list[str]:
        return [c.name for c in self.controls]


# ---------------------------------------------------------------------------
# Capability registry — declarative, data-driven (SRS 3.2 Hardware Interfaces).
# ---------------------------------------------------------------------------
_POWER = Control(
    name="power", label="Power", kind=ControlKind.TOGGLE, values=("on", "off"), default="off"
)

CAPABILITIES: dict[DeviceType, CapabilitySchema] = {
    DeviceType.PLUG: CapabilitySchema(
        type=DeviceType.PLUG,
        display_name="Smart Plug",
        telemetry=("power_w", "kwh_total", "online"),
        controls=(_POWER,),
        nominal_power_w=60.0,
    ),
    DeviceType.BULB: CapabilitySchema(
        type=DeviceType.BULB,
        display_name="Smart Bulb",
        telemetry=("power_w", "kwh_total", "brightness", "online"),
        controls=(
            _POWER,
            Control(
                name="brightness", label="Brightness", kind=ControlKind.RANGE,
                unit="%", min=0, max=100, step=1, default=80,
            ),
        ),
        nominal_power_w=9.0,
    ),
    DeviceType.FAN: CapabilitySchema(
        type=DeviceType.FAN,
        display_name="Fan",
        telemetry=("power_w", "kwh_total", "speed", "mode", "online"),
        controls=(
            _POWER,
            Control(
                name="speed", label="Speed", kind=ControlKind.RANGE,
                min=0, max=5, step=1, default=2,
            ),
            Control(
                name="mode", label="Mode", kind=ControlKind.ENUM,
                values=("normal", "natural", "sleep"), default="normal",
            ),
        ),
        nominal_power_w=45.0,
    ),
    DeviceType.AC: CapabilitySchema(
        type=DeviceType.AC,
        display_name="Air Conditioner",
        telemetry=("power_w", "kwh_total", "temperature", "target", "mode", "online"),
        controls=(
            _POWER,
            Control(
                name="target", label="Target temperature", kind=ControlKind.RANGE,
                unit="°C", min=16, max=30, step=1, default=26, safety_sensitive=True,
            ),
            Control(
                name="mode", label="Mode", kind=ControlKind.ENUM,
                values=("cool", "fan", "dry", "auto"), default="cool",
            ),
        ),
        nominal_power_w=900.0,
    ),
    DeviceType.SENSOR: CapabilitySchema(
        type=DeviceType.SENSOR,
        display_name="Environment Sensor",
        telemetry=("temperature", "humidity", "occupancy", "online"),
        controls=(),  # read-only
        reversible=False,
        nominal_power_w=0.5,
    ),
}


def get_capability(device_type: DeviceType) -> CapabilitySchema:
    return CAPABILITIES[device_type]


@dataclass
class ValidationResult:
    ok: bool
    error: str | None = None
    normalized: Any = None


def validate_command(device_type: DeviceType, control_name: str, value: Any) -> ValidationResult:
    """Validate a single (control, value) against the capability schema (REQ-4.2.3)."""
    schema = CAPABILITIES.get(device_type)
    if schema is None:
        return ValidationResult(False, f"Unknown device type '{device_type}'")
    control = schema.control(control_name)
    if control is None:
        return ValidationResult(
            False,
            f"Device type '{device_type.value}' has no control '{control_name}' "
            f"(allowed: {schema.control_names()})",
        )
    if control.kind == ControlKind.READONLY:
        return ValidationResult(False, f"Control '{control_name}' is read-only")
    if control.kind == ControlKind.TOGGLE:
        v = str(value).lower()
        allowed = control.values or ("on", "off")
        if v not in allowed:
            return ValidationResult(False, f"'{control_name}' must be one of {list(allowed)}")
        return ValidationResult(True, normalized=v)
    if control.kind == ControlKind.ENUM:
        v = str(value)
        if control.values is None or v not in control.values:
            return ValidationResult(False, f"'{control_name}' must be one of {list(control.values or ())}")
        return ValidationResult(True, normalized=v)
    if control.kind == ControlKind.RANGE:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return ValidationResult(False, f"'{control_name}' must be numeric")
        if control.min is not None and num < control.min:
            return ValidationResult(False, f"'{control_name}' must be >= {control.min}")
        if control.max is not None and num > control.max:
            return ValidationResult(False, f"'{control_name}' must be <= {control.max}")
        # Snap integers when step is whole.
        if control.step and float(control.step).is_integer():
            num = float(round(num))
        return ValidationResult(True, normalized=num)
    return ValidationResult(False, f"Unsupported control kind '{control.kind}'")
