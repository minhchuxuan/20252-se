"""Habit-learning & recommendation engine (REQ-4.4.x).

Deterministic, explainable habit miners detect three wasteful patterns from
telemetry and turn them into readable WHEN-THEN recommendations ranked by VND
saving. No black-box model (Design Constraint).

Miners:
  1. idle_plug      — a (non-safety-critical) plug drawing power overnight.
  2. light_when_empty — a bulb left on while the room is unoccupied.
  3. ac_too_cold    — an AC habitually set below 26 °C.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..core.clock import now
from ..core.events import EventType, bus
from ..domain.enums import DeviceType, RecommendationStatus, RuleSource
from ..domain.models import Device, Recommendation
from ..repositories import (
    DeviceRepository,
    ReadingRepository,
    RecommendationRepository,
)
from .optimization_service import OptimizationService
from .rule_engine import RuleEngine

# Only surface a recommendation if it saves at least this much per month.
_MIN_SAVING_VND = 3000.0
_NIGHT_WINDOW = ("00:00", "06:00")


class RecommendationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = RecommendationRepository(db)
        self.devices = DeviceRepository(db)
        self.readings = ReadingRepository(db)
        self.optimizer = OptimizationService(db)
        self.engine = RuleEngine(db)

    # ----------------------------------------------------------- public
    def list_active(self, home_id: int) -> list[Recommendation]:
        recs = self.repo.active_for_home(home_id)
        recs.sort(key=lambda r: r.estimated_monthly_saving_vnd, reverse=True)
        return recs[: settings.recommendation_max_active]

    def analyze(self, home_id: int) -> list[Recommendation]:
        """Run miners, persist new recommendations, enforce caps/suppression."""
        candidates: list[dict] = []
        for device in self.devices.by_home(home_id):
            candidates.extend(self._mine_device(device))

        created: list[Recommendation] = []
        for cand in candidates:
            if cand["estimated_monthly_saving_vnd"] < _MIN_SAVING_VND:
                continue
            if not self._is_allowed(home_id, cand["signature"]):
                continue
            rec = self.repo.add(
                Recommendation(
                    home_id=home_id, device_id=cand["device_id"], title=cand["title"],
                    when_json=cand["when"], then_json=cand["then"], until_json=cand.get("until"),
                    rationale=cand["rationale"],
                    data_window_start=cand["window_start"], data_window_end=cand["window_end"],
                    estimated_monthly_saving_vnd=cand["estimated_monthly_saving_vnd"],
                    signature=cand["signature"], status=RecommendationStatus.ACTIVE,
                )
            )
            created.append(rec)
            bus.publish(
                EventType.RECOMMENDATION_READY,
                {"home_id": home_id, "recommendation_id": rec.id, "title": "New saving idea: " + rec.title,
                 "body": f"Estimated saving ≈ {rec.estimated_monthly_saving_vnd:,.0f} VND/month"},
            )
        self.db.commit()
        self._enforce_max_active(home_id)
        return self.list_active(home_id)

    def accept(self, rec_id: int, home_id: int, name: str | None, auto_apply: bool):
        from ..schemas.common import Action, Condition
        from ..schemas.rule import RuleCreate

        rec = self._get(rec_id, home_id)
        data = RuleCreate(
            name=name or rec.title,
            device_id=rec.device_id,
            when=Condition(**rec.when_json),
            then=Action(**rec.then_json),
            until=Condition(**rec.until_json) if rec.until_json else None,
            enabled=True,
            auto_apply=auto_apply,
        )
        rule = self.engine.create(home_id, None, data, source=RuleSource.RECOMMENDATION)
        rec.status = RecommendationStatus.ACCEPTED
        self.db.commit()
        return rule

    def dismiss(self, rec_id: int, home_id: int) -> Recommendation:
        rec = self._get(rec_id, home_id)
        rec.status = RecommendationStatus.DISMISSED
        rec.dismissed_until = now() + timedelta(days=settings.recommendation_dismiss_days)
        self.db.commit()
        return rec

    # ----------------------------------------------------------- miners
    def _mine_device(self, device: Device) -> list[dict]:
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

    def _mine_idle_plug(self, device: Device) -> list[dict]:
        if device.safety_critical or not self._has_enough_data(device.id):
            return []
        night_hours = {0, 1, 2, 3, 4, 5}
        night_kwh_day = self.optimizer.window_baseline_kwh(device.id, night_hours)
        if night_kwh_day < 0.02:  # essentially off at night already
            return []
        when = {"type": "time", "between": list(_NIGHT_WINDOW)}
        then = {"control": "power", "value": "off"}
        est = self.optimizer.estimate_rule(device, when, then)
        ws, we = self._window()
        return [{
            "device_id": device.id,
            "title": f"Turn off {device.name} overnight",
            "when": when, "then": then,
            "rationale": (
                f"{device.name} draws about {night_kwh_day:.2f} kWh every night "
                f"(00:00–06:00) while it is likely unused. Switching it off in that "
                f"window avoids the standby draw."
            ),
            "window_start": ws, "window_end": we,
            "estimated_monthly_saving_vnd": est.saved_vnd_month,
            "signature": f"{device.id}:idle_plug_night",
        }]

    def _mine_light_when_empty(self, device: Device) -> list[dict]:
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
        then = {"control": "power", "value": "off"}
        est = self.optimizer.estimate_rule(device, when, then)
        ws, we = self._window()
        return [{
            "device_id": device.id,
            "title": f"Turn off {device.name} when the room is empty",
            "when": when, "then": then,
            "rationale": (
                f"{device.name} stays on for about {wasted_kwh_day:.2f} kWh/day while the "
                f"room is unoccupied. Turning it off after the room is empty for 15 minutes "
                f"removes that waste."
            ),
            "window_start": ws, "window_end": we,
            "estimated_monthly_saving_vnd": est.saved_vnd_month,
            "signature": f"{device.id}:light_when_empty",
        }]

    def _mine_ac_too_cold(self, device: Device) -> list[dict]:
        if not self._has_enough_data(device.id):
            return []
        current_target = float((device.state or {}).get("target", 26))
        if current_target >= 26:
            return []
        when = {"type": "time", "between": ["22:00", "06:00"]}
        then = {"control": "target", "value": 26}
        est = self.optimizer.estimate_rule(device, when, then)
        if est.saved_vnd_month < _MIN_SAVING_VND:
            return []
        ws, we = self._window()
        return [{
            "device_id": device.id,
            "title": f"Raise {device.name} to 26°C at night",
            "when": when, "then": then,
            "rationale": (
                f"{device.name} is habitually set to {current_target:.0f}°C overnight. Raising the "
                f"target to 26°C between 22:00–06:00 keeps comfort while cutting compressor runtime."
            ),
            "window_start": ws, "window_end": we,
            "estimated_monthly_saving_vnd": est.saved_vnd_month,
            "signature": f"{device.id}:ac_too_cold",
        }]

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

    def _is_allowed(self, home_id: int, signature: str) -> bool:
        """No duplicate active rec; respect 30-day dismissal (REQ-4.4.5)."""
        for existing in self.repo.by_signature(home_id, signature):
            if existing.status == RecommendationStatus.ACTIVE:
                return False
            if existing.status == RecommendationStatus.ACCEPTED:
                return False
            if (
                existing.status == RecommendationStatus.DISMISSED
                and existing.dismissed_until
                and existing.dismissed_until > now()
            ):
                return False
        return True

    def _enforce_max_active(self, home_id: int) -> None:
        active = self.repo.active_for_home(home_id)
        active.sort(key=lambda r: r.estimated_monthly_saving_vnd, reverse=True)
        for extra in active[settings.recommendation_max_active:]:
            extra.status = RecommendationStatus.EXPIRED
        self.db.commit()

    def _get(self, rec_id: int, home_id: int) -> Recommendation:
        from ..core.errors import NotFoundError

        rec = self.db.get(Recommendation, rec_id)
        if rec is None or rec.home_id != home_id:
            raise NotFoundError("Recommendation not found")
        return rec
