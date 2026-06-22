"""Recommendation provider port (Strategy) — the swappable "AI" boundary.

Finding the habit is the AI concern that the client (an AI contractor) supplies. SHEO
therefore depends only on this *port*, never on a concrete miner: the shipped default is a
deterministic, explainable provider, and a black-box ML provider implementing the same
interface can be substituted at the composition root without touching the API, the UI, the
rule engine, or the VND estimator (which remain SHEO's own software).

A provider only *detects habits* and proposes candidate WHEN-THEN rules. It deliberately
carries no money: the VND saving (REQ-4.5) is computed by SHEO's ``OptimizationService``,
so the most valued, client-facing logic stays inside SHEO and out of the black box.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..core.clock import now
from ..domain.enums import DeviceType
from ..domain.models import Device
from ..repositories import DeviceRepository, ReadingRepository
from .optimization_service import OptimizationService

_NIGHT_WINDOW = ("00:00", "06:00")


@dataclass
class RecommendationCandidate:
    """A detected habit expressed as a candidate WHEN-THEN rule.

    Carries no VND figure on purpose — pricing is SHEO's job, not the provider's."""
    device_id: int
    title: str
    when: dict
    then: dict
    rationale: str
    signature: str
    window_start: datetime
    window_end: datetime
    until: dict | None = None


class RecommendationProvider(ABC):
    """Port: turn a unit's telemetry history into candidate rules to consider."""

    @abstractmethod
    def mine(self, home_id: int) -> list[RecommendationCandidate]:
        """Return candidate habit rules for the given unit (may be empty)."""
        raise NotImplementedError


class HeuristicRecommendationProvider(RecommendationProvider):
    """Default provider: deterministic, explainable habit miners (no black-box model).

    Detects three wasteful patterns from telemetry:
      1. idle_plug        — a (non-safety-critical) plug drawing power overnight.
      2. light_when_empty — a bulb left on while the room is unoccupied.
      3. ac_too_cold      — an AC habitually set below 26 C.
    """

    def __init__(self, db: Session):
        self.db = db
        self.devices = DeviceRepository(db)
        self.readings = ReadingRepository(db)
        # Used only for usage (kWh) analysis of the history, never for pricing.
        self.optimizer = OptimizationService(db)

    def mine(self, home_id: int) -> list[RecommendationCandidate]:
        out: list[RecommendationCandidate] = []
        for device in self.devices.by_home(home_id):
            out.extend(self._mine_device(device))
        return out

    # ----------------------------------------------------------- miners
    def _mine_device(self, device: Device) -> list[RecommendationCandidate]:
        if device.type == DeviceType.PLUG:
            return self._mine_idle_plug(device)
        if device.type == DeviceType.BULB:
            return self._mine_light_when_empty(device)
        if device.type == DeviceType.AC:
            return self._mine_ac_too_cold(device)
        return []

    def _has_enough_data(self, device_id: int) -> bool:
        """REQ-4.4.1: at least 7 days of telemetry."""
        first = self.readings.first_reading_ts(device_id)
        return first is not None and (now() - first) >= timedelta(days=settings.recommendation_min_days)

    def _window(self) -> tuple:
        end = now()
        return end - timedelta(days=settings.baseline_days), end

    def _mine_idle_plug(self, device: Device) -> list[RecommendationCandidate]:
        if device.safety_critical or not self._has_enough_data(device.id):
            return []
        night_hours = {0, 1, 2, 3, 4, 5}
        night_kwh_day = self.optimizer.window_baseline_kwh(device.id, night_hours)
        if night_kwh_day < 0.02:  # essentially off at night already
            return []
        ws, we = self._window()
        return [RecommendationCandidate(
            device_id=device.id,
            title=f"Turn off {device.name} overnight",
            when={"type": "time", "between": list(_NIGHT_WINDOW)},
            then={"control": "power", "value": "off"},
            rationale=(
                f"{device.name} draws about {night_kwh_day:.2f} kWh every night "
                f"(00:00–06:00) while it is likely unused. Switching it off in that "
                f"window avoids the standby draw."
            ),
            signature=f"{device.id}:idle_plug_night",
            window_start=ws, window_end=we,
        )]

    def _mine_light_when_empty(self, device: Device) -> list[RecommendationCandidate]:
        if not self._has_enough_data(device.id):
            return []
        sensor = self._find_sensor(device.home_id)
        empty_hours = self._empty_hours(sensor.id) if sensor else {23, 0, 1, 2, 3, 4, 5}
        wasted_kwh_day = self.optimizer.window_baseline_kwh(device.id, empty_hours)
        if wasted_kwh_day < 0.01:
            return []
        if sensor is not None:
            when = {"type": "occupancy", "device_id": sensor.id, "value": False, "for_minutes": 15}
        else:
            when = {"type": "time", "between": ["23:00", "06:00"]}
        ws, we = self._window()
        return [RecommendationCandidate(
            device_id=device.id,
            title=f"Turn off {device.name} when the room is empty",
            when=when,
            then={"control": "power", "value": "off"},
            rationale=(
                f"{device.name} stays on for about {wasted_kwh_day:.2f} kWh/day while the "
                f"room is unoccupied. Turning it off after the room is empty for 15 minutes "
                f"removes that waste."
            ),
            signature=f"{device.id}:light_when_empty",
            window_start=ws, window_end=we,
        )]

    def _mine_ac_too_cold(self, device: Device) -> list[RecommendationCandidate]:
        if not self._has_enough_data(device.id):
            return []
        current_target = float((device.state or {}).get("target", 26))
        if current_target >= 26:
            return []
        ws, we = self._window()
        return [RecommendationCandidate(
            device_id=device.id,
            title=f"Raise {device.name} to 26°C at night",
            when={"type": "time", "between": ["22:00", "06:00"]},
            then={"control": "target", "value": 26},
            rationale=(
                f"{device.name} is habitually set to {current_target:.0f}°C overnight. Raising the "
                f"target to 26°C between 22:00–06:00 keeps comfort while cutting compressor runtime."
            ),
            signature=f"{device.id}:ac_too_cold",
            window_start=ws, window_end=we,
        )]

    # ----------------------------------------------------------- helpers
    def _find_sensor(self, home_id: int) -> Device | None:
        for d in self.devices.by_home(home_id):
            if d.type == DeviceType.SENSOR:
                return d
        return None

    def _empty_hours(self, sensor_id: int) -> set[int]:
        """Hours of day that are mostly unoccupied, derived from sensor telemetry."""
        start, end = self._window()
        readings = self.readings.in_range(sensor_id, start, end)
        occ_true = [0] * 24
        occ_total = [0] * 24
        for r in readings:
            if r.occupancy is None:
                continue
            occ_total[r.ts.hour] += 1
            if r.occupancy:
                occ_true[r.ts.hour] += 1
        empty = set()
        for h in range(24):
            if occ_total[h] and (occ_true[h] / occ_total[h]) < 0.25:
                empty.add(h)
        return empty or {23, 0, 1, 2, 3, 4, 5}
