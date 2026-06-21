"""Device adapter abstraction — the Strategy pattern (SE Intro 14).

Each device *type* has different command semantics and a different power model.
Instead of branching on type throughout the codebase, behaviour is encapsulated
in one ``DeviceAdapter`` strategy per type. The capability schema validates
*what* may be sent; the adapter decides *how* the (simulated) device reacts.

Real hardware would implement the same interface by talking to a vendor API —
satisfying the SRS maintainability goal: "adding a new device type shall require
changes in the device adapter and capability schema only".
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any

from ..domain.capability import CapabilitySchema, get_capability
from ..domain.enums import DeviceType


class DeviceAdapter(ABC):
    """Strategy interface. Stateless: state lives in the Device row / a dict."""

    device_type: DeviceType

    @property
    def schema(self) -> CapabilitySchema:
        return get_capability(self.device_type)

    def default_state(self) -> dict[str, Any]:
        """Initial state for a new mock device, derived from capability defaults."""
        state: dict[str, Any] = {}
        for control in self.schema.controls:
            if control.default is not None:
                state[control.name] = control.default
        state.setdefault("power_w", 0.0)
        return state

    def apply_control(self, state: dict[str, Any], control: str, value: Any) -> dict[str, Any]:
        """Apply a single validated control change, returning the new state."""
        new_state = dict(state)
        new_state[control] = value
        if control == "power" and value == "off":
            new_state["power_w"] = 0.0
        return new_state

    @abstractmethod
    def tick(self, state: dict[str, Any], dt_seconds: float, ctx: dict[str, Any]) -> dict[str, Any]:
        """Advance the simulated device by ``dt_seconds`` given world ``ctx``.

        Returns a new state dict that includes an updated ``power_w`` (and, for
        applicable types, derived telemetry such as AC ``temperature``).
        """
        raise NotImplementedError

    @staticmethod
    def _noise(value: float, pct: float = 0.05) -> float:
        return max(0.0, value * (1.0 + random.uniform(-pct, pct)))

    @staticmethod
    def interval_kwh(power_w: float, dt_seconds: float) -> float:
        """Energy (kWh) drawn over the interval: W * h / 1000."""
        return power_w * (dt_seconds / 3600.0) / 1000.0
