"""Concrete device adapters (Strategy implementations).

Each adapter models a realistic, deterministic power profile so the dashboard,
baselines, habit miner and savings engine all have meaningful data — without any
real hardware (REQ-4.2.5).
"""
from __future__ import annotations

import random
from typing import Any

from ..domain.enums import DeviceType
from .base import DeviceAdapter


class PlugAdapter(DeviceAdapter):
    device_type = DeviceType.PLUG

    def tick(self, state, dt_seconds, ctx):
        s = dict(state)
        if s.get("power") == "on":
            # A plug carries an attached load. ``load_w`` lets a seeded device act
            # as a standby drain (e.g. idle TV ~15W) or an active appliance.
            base = float(s.get("load_w", self.schema.nominal_power_w))
            s["power_w"] = self._noise(base, 0.04)
        else:
            s["power_w"] = 0.0
        return s


class BulbAdapter(DeviceAdapter):
    device_type = DeviceType.BULB

    def tick(self, state, dt_seconds, ctx):
        s = dict(state)
        if s.get("power") == "on":
            brightness = float(s.get("brightness", 80))
            s["power_w"] = self._noise(self.schema.nominal_power_w * brightness / 100.0, 0.03)
        else:
            s["power_w"] = 0.0
        return s


class FanAdapter(DeviceAdapter):
    device_type = DeviceType.FAN

    def tick(self, state, dt_seconds, ctx):
        s = dict(state)
        speed = int(s.get("speed", 0))
        if s.get("power") == "on" and speed > 0:
            # ~10W electronics baseline + ~8W per speed step.
            base = 10.0 + speed * 8.0
            if s.get("mode") == "sleep":
                base *= 0.85
            s["power_w"] = self._noise(base, 0.05)
        else:
            s["power_w"] = 0.0
        return s


class ACAdapter(DeviceAdapter):
    device_type = DeviceType.AC

    HYSTERESIS = 0.5  # deg C
    FAN_ONLY_W = 120.0
    COMPRESSOR_W = 900.0

    def default_state(self):
        s = super().default_state()
        s.setdefault("temperature", 30.0)   # room starts warm
        s.setdefault("compressor_on", False)
        return s

    def tick(self, state, dt_seconds, ctx):
        s = dict(state)
        ambient = float(ctx.get("ambient_temp", 31.0))
        temp = float(s.get("temperature", ambient))
        if s.get("power") != "on" or s.get("mode") == "fan":
            # No active cooling: room drifts toward ambient.
            temp += (ambient - temp) * min(1.0, dt_seconds / 1800.0)
            s["temperature"] = round(temp, 2)
            s["compressor_on"] = False
            s["power_w"] = self.FAN_ONLY_W if s.get("power") == "on" else 0.0
            return s

        target = float(s.get("target", 26))
        # Compressor thermostat with hysteresis.
        compressor = bool(s.get("compressor_on", False))
        if temp > target + self.HYSTERESIS:
            compressor = True
        elif temp <= target:
            compressor = False

        if compressor:
            # Cool toward target; cooling rate scaled by how hard it works.
            temp -= 1.2 * (dt_seconds / 1800.0) * (1.0 + max(0.0, ambient - target) / 10.0)
            # Power rises with the ambient/target gap (lower target => more work).
            load = self.COMPRESSOR_W * (0.7 + 0.3 * min(1.0, max(0.0, ambient - target) / 12.0))
            s["power_w"] = self._noise(load, 0.04)
        else:
            temp += (ambient - temp) * min(1.0, dt_seconds / 3600.0)
            s["power_w"] = self.FAN_ONLY_W

        s["temperature"] = round(temp, 2)
        s["compressor_on"] = compressor
        return s


class SensorAdapter(DeviceAdapter):
    device_type = DeviceType.SENSOR

    def default_state(self):
        return {"temperature": 30.0, "humidity": 70.0, "occupancy": False, "power_w": 0.5}

    def tick(self, state, dt_seconds, ctx):
        s = dict(state)
        s["temperature"] = round(self._noise(float(ctx.get("ambient_temp", 30.0)), 0.01), 2)
        s["humidity"] = round(min(95.0, max(40.0, 70.0 + random.uniform(-5, 5))), 1)
        # Occupancy is supplied by the world model (per-room schedule).
        if "occupied" in ctx:
            s["occupancy"] = bool(ctx["occupied"])
        s["power_w"] = 0.5
        return s


_ADAPTERS: dict[DeviceType, DeviceAdapter] = {
    DeviceType.PLUG: PlugAdapter(),
    DeviceType.BULB: BulbAdapter(),
    DeviceType.FAN: FanAdapter(),
    DeviceType.AC: ACAdapter(),
    DeviceType.SENSOR: SensorAdapter(),
}


def get_adapter(device_type: DeviceType) -> DeviceAdapter:
    """Strategy selector."""
    return _ADAPTERS[device_type]
