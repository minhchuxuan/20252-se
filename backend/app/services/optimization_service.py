"""Optimization Engine & bill-saving estimation (REQ-4.5.x).

Explainable and rule-based (Design Constraint). Every estimate reduces to the
SRS formula:

    saved_vnd = sum((baseline_kWh - expected_kWh_with_rule) * tariff_VND_per_kWh)

Two estimation paths share this formula:
  * generic rule estimate (user-authored rule, REQ-4.5.3) — uses a 14-day
    hourly baseline profile and a transparent per-action model;
  * habit recommendation — the miner measures the wasted energy directly and
    passes it in as ``baseline_kwh`` with ``expected_kwh = 0`` (full avoidance).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..core.clock import now
from ..core.timeutil import current_billing_cycle, days_in_cycle, hour_set_from_window
from ..domain.enums import DeviceType, SavingsKind
from ..domain.models import Device
from ..repositories import DeviceRepository, ReadingRepository, SavingsRepository
from ..schemas.savings import SavingsEstimate, SavingsSummary
from .tariff_service import TariffService

# Transparent per-action coefficients (documented in SDD / optimization notes).
AC_SAVING_PER_DEGREE = 0.06   # ~6% AC energy per +1 °C of target (industry rule of thumb)
AC_MAX_SAVING_FRACTION = 0.45


class OptimizationService:
    def __init__(self, db: Session):
        self.db = db
        self.devices = DeviceRepository(db)
        self.readings = ReadingRepository(db)
        self.savings = SavingsRepository(db)
        self.tariffs = TariffService(db)

    # ----------------------------------------------------------- baselines
    def baseline_daily_kwh(self, device_id: int, days: int | None = None) -> float:
        """Average kWh/day over the previous ``days`` (REQ-4.5.1: default 14)."""
        days = days or settings.baseline_days
        end = now()
        start = end - timedelta(days=days)
        total = self.readings.sum_energy(device_id, start, end)
        first = self.readings.first_reading_ts(device_id)
        if first is None:
            return 0.0
        span_days = max(1.0, min(days, (end - max(first, start)).total_seconds() / 86400.0))
        return total / span_days

    def hourly_baseline_kwh(self, device_id: int, days: int | None = None) -> list[float]:
        """Average kWh consumed in each hour-of-day (index 0..23) per day."""
        days = days or settings.baseline_days
        end = now()
        start = end - timedelta(days=days)
        readings = self.readings.in_range(device_id, start, end)
        buckets = [0.0] * 24
        day_span = max(1.0, (end - start).total_seconds() / 86400.0)
        for r in readings:
            buckets[r.ts.hour] += r.interval_kwh or 0.0
        return [b / day_span for b in buckets]

    def window_baseline_kwh(self, device_id: int, hours: set[int]) -> float:
        """Baseline kWh/day consumed during the given hours-of-day."""
        hourly = self.hourly_baseline_kwh(device_id)
        return sum(hourly[h] for h in hours if 0 <= h < 24)

    def home_monthly_kwh(self, home_id: int) -> float:
        """Estimated monthly kWh for the whole home (for tiered marginal pricing)."""
        total = 0.0
        for d in self.devices.by_home(home_id):
            total += self.baseline_daily_kwh(d.id) * 30
        return total

    # ----------------------------------------------------------- estimation
    def estimate_rule(
        self, device: Device, when: dict, then: dict, until: dict | None = None
    ) -> SavingsEstimate:
        """Estimate monthly saving of a candidate rule (REQ-4.5.2/4.5.3)."""
        tariff = self.tariffs.active(device.home_id)
        price = self.tariffs.effective_price(tariff, monthly_kwh=self.home_monthly_kwh(device.home_id))

        hours = self._affected_hours(when)
        window_kwh_day = self.window_baseline_kwh(device.id, hours)
        expected_kwh_day = self._expected_window_kwh(device, then, window_kwh_day)
        saved_day = max(0.0, window_kwh_day - expected_kwh_day)

        baseline_month = window_kwh_day * 30
        expected_month = expected_kwh_day * 30
        saved_month = saved_day * 30
        saved_vnd = saved_month * price

        explanation = self._explain(device, when, then, hours, window_kwh_day, expected_kwh_day, price)
        return SavingsEstimate(
            baseline_kwh_month=round(baseline_month, 2),
            expected_kwh_month=round(expected_month, 2),
            saved_kwh_month=round(saved_month, 2),
            saved_vnd_month=round(saved_vnd, 0),
            tariff_vnd_per_kwh=round(price, 1),
            explanation=explanation,
        )

    def estimate_value_vnd(self, device: Device, when: dict, then: dict, until: dict | None = None) -> float:
        return self.estimate_rule(device, when, then, until).saved_vnd_month

    def measured_to_vnd(self, home_id: int, saved_kwh: float) -> float:
        tariff = self.tariffs.active(home_id)
        return saved_kwh * self.tariffs.effective_price(tariff, monthly_kwh=self.home_monthly_kwh(home_id))

    # ----------------------------------------------------------- cycle savings
    def savings_summary(self, home_id: int) -> SavingsSummary:
        """Savings so far in the current billing cycle (REQ-4.5.4)."""
        from ..core.errors import PermissionDeniedError
        from ..domain.models import Home

        if home_id is None:
            raise PermissionDeniedError("The administrator has no unit; use the building overview")
        home = self.db.get(Home, home_id)
        billing_day = home.billing_cycle_day if home else 1
        cycle_start, cycle_end = current_billing_cycle(now(), billing_day)
        records = self.savings.measured_in_period(home_id, cycle_start, cycle_end)
        saved_kwh = sum(r.saved_kwh for r in records)
        saved_vnd = sum(r.saved_vnd for r in records)

        # Project month estimate from active accepted rules.
        from ..repositories import RuleRepository

        rules = RuleRepository(self.db).enabled_by_home(home_id)
        est_month = sum(r.estimated_monthly_saving_vnd for r in rules)
        tariff = self.tariffs.active(home_id)
        return SavingsSummary(
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            saved_kwh_cycle=round(saved_kwh, 2),
            saved_vnd_cycle=round(saved_vnd, 0),
            estimated_saved_vnd_month=round(est_month, 0),
            currency=tariff.currency,
        )

    def accrue_savings(self, home_id: int, dt_seconds: float) -> float:
        """Accrue *measured* savings for rules actively keeping a device in its
        saved state during this interval (REQ-4.5.4). Returns VND accrued.

        For each enabled rule whose WHEN currently holds and whose device is in
        the rule's target state, the avoided power (baseline − actual) over the
        interval is converted to kWh and priced, then folded into a per-rule
        MEASURED SavingsRecord for the current billing cycle.
        """
        from ..domain.enums import SavingsKind
        from ..domain.models import Home, Rule, SavingsRecord
        from ..repositories import RuleRepository
        from .rule_engine import RuleEngine

        home = self.db.get(Home, home_id)
        billing_day = home.billing_cycle_day if home else 1
        cycle_start, cycle_end = current_billing_cycle(now(), billing_day)
        tariff = self.tariffs.active(home_id)
        price = self.tariffs.effective_price(tariff, monthly_kwh=self.home_monthly_kwh(home_id))
        engine = RuleEngine(self.db)

        accrued = 0.0
        for rule in RuleRepository(self.db).enabled_by_home(home_id):
            device = self.devices.get(rule.device_id)
            if device is None:
                continue
            control = rule.then_json.get("control")
            target_value = rule.then_json.get("value")
            in_target = str((device.state or {}).get(control)) == str(target_value)
            if not (in_target and engine.evaluate(rule)):
                continue
            hour = now().hour
            baseline_w = self.hourly_baseline_kwh(device.id)[hour] * 1000.0  # kWh/h == kW avg
            actual_w = float((device.state or {}).get("power_w", 0.0))
            avoided_w = max(0.0, baseline_w - actual_w)
            inc_kwh = avoided_w * (dt_seconds / 3600.0) / 1000.0
            if inc_kwh <= 0:
                continue
            inc_vnd = inc_kwh * price
            record = next(
                (r for r in self.savings.measured_in_period(home_id, cycle_start, cycle_end)
                 if r.rule_id == rule.id),
                None,
            )
            if record is None:
                record = self.savings.add(
                    SavingsRecord(
                        home_id=home_id, rule_id=rule.id, device_id=device.id,
                        period_start=cycle_start, period_end=now(),
                        kind=SavingsKind.MEASURED,
                    )
                )
            record.saved_kwh += inc_kwh
            record.saved_vnd += inc_vnd
            record.period_end = now()
            accrued += inc_vnd
        if accrued:
            self.db.commit()
        return accrued

    def check_drift(self, rule_id: int) -> bool:
        """REQ-4.5.5: measured within +/-20% of estimate, else needs recalculation."""
        from ..domain.models import Home, Rule

        rule = self.db.get(Rule, rule_id)
        if rule is None or rule.estimated_monthly_saving_vnd <= 0:
            return False
        home = self.db.get(Home, rule.home_id)
        cycle_start, cycle_end = current_billing_cycle(now(), home.billing_cycle_day if home else 1)
        records = [
            r for r in self.savings.measured_in_period(rule.home_id, cycle_start, cycle_end)
            if r.rule_id == rule_id
        ]
        if not records:
            return False
        measured = sum(r.saved_vnd for r in records)
        estimate = rule.estimated_monthly_saving_vnd
        # Compare like-for-like periods (REQ-4.5.5). The estimate is a whole-month
        # figure, but ``measured`` only accrues while the rule actually exists, so the
        # observation window must start at the later of the cycle start and the rule's
        # creation -- otherwise a rule created mid-cycle is compared against a full
        # month of expected saving and reads as drifting from the moment it is made.
        total_days = days_in_cycle(cycle_start, cycle_end)
        observation_start = max(cycle_start, rule.created_at)
        observed_days = max(0.0, days_in_cycle(observation_start, now()))
        # A brand-new rule has not had time to save yet; don't flag drift until it has
        # been observed long enough for the measured sample to be meaningful.
        if observed_days < settings.savings_drift_min_days:
            rule.needs_recalculation = False
            self.db.commit()
            return False
        expected_so_far = estimate * (observed_days / total_days) if total_days > 0 else 0.0
        if expected_so_far <= 0:
            return False
        drift = abs(measured - expected_so_far) / expected_so_far
        rule.needs_recalculation = drift > settings.savings_drift_threshold
        self.db.commit()
        return rule.needs_recalculation

    # ----------------------------------------------------------- internals
    @staticmethod
    def _affected_hours(when: dict) -> set[int]:
        kind = when.get("type")
        if kind == "time":
            if when.get("between"):
                a, b = when["between"]
                return hour_set_from_window(a, b)
            if when.get("at"):
                # Single-time switch-off with no UNTIL: assume an overnight idle block.
                h = int(when["at"].split(":")[0])
                return {(h + i) % 24 for i in range(8)}
        if kind == "occupancy" and when.get("value") in (False, "false"):
            # Hours the home is typically empty (weekday schedule proxy).
            from ..simulator.world import is_occupied
            from datetime import datetime, timezone

            ref = datetime(2026, 1, 5, tzinfo=timezone.utc)  # a Monday
            return {h for h in range(24) if not is_occupied(ref.replace(hour=h))}
        # device_state / tariff_window / day: assume all-day applicability.
        return set(range(24))

    def _expected_window_kwh(self, device: Device, then: dict, window_kwh_day: float) -> float:
        control = then.get("control")
        value = then.get("value")
        if control == "power" and str(value).lower() == "off":
            return 0.0
        if device.type == DeviceType.AC and control == "target":
            current = float(device.state.get("target", 26))
            delta = float(value) - current
            if delta > 0:  # raising target saves energy
                frac = min(AC_MAX_SAVING_FRACTION, AC_SAVING_PER_DEGREE * delta)
                return window_kwh_day * (1 - frac)
            return window_kwh_day
        if device.type == DeviceType.FAN and control == "speed":
            cur = max(1, int(device.state.get("speed", 3)))
            new = max(0, int(value))
            cur_p, new_p = 10 + cur * 8, (10 + new * 8 if new > 0 else 0)
            return window_kwh_day * (new_p / cur_p)
        if device.type == DeviceType.BULB and control == "brightness":
            cur = max(1.0, float(device.state.get("brightness", 80)))
            return window_kwh_day * (float(value) / cur)
        return window_kwh_day

    @staticmethod
    def _explain(device, when, then, hours, base_kwh, exp_kwh, price) -> str:
        saved = max(0.0, base_kwh - exp_kwh)
        hrs = sorted(hours)
        contiguous = bool(hrs) and (hrs[-1] - hrs[0] + 1 == len(hrs))
        window = (
            f"{hrs[0]:02d}:00–{(hrs[-1] + 1) % 24:02d}:00"
            if contiguous and len(hrs) < 24 else "the applicable hours"
        )
        return (
            f"Baseline use of {device.name} during {window} is ~{base_kwh:.2f} kWh/day; "
            f"with this rule it drops to ~{exp_kwh:.2f} kWh/day, saving ~{saved:.2f} kWh/day "
            f"× 30 days × {price:,.0f} VND/kWh."
        )
