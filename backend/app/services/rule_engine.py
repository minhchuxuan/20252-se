"""Rule engine: authoring, validation, conflict detection, evaluation, execution,
and undo (REQ-4.3.x). Deterministic and explainable.

A rule is ``WHEN <condition> THEN <action> [UNTIL <stop>]`` targeting one device.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..core.clock import now
from ..core.errors import ConflictError, NotFoundError, ValidationError
from ..core.events import EventType, bus
from ..domain.capability import get_capability, validate_command
from ..domain.enums import (
    CommandOutcome,
    DeviceType,
    Initiator,
    RuleSource,
)
from ..domain.models import Device, Rule, RuleExecution
from ..repositories import (
    DeviceRepository,
    ReadingRepository,
    RuleExecutionRepository,
    RuleRepository,
)
from .device_service import DeviceService
from .optimization_service import OptimizationService
from .tariff_service import TariffService

_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_FIRE_COOLDOWN_SECONDS = 90


class RuleEngine:
    def __init__(self, db: Session):
        self.db = db
        self.rules = RuleRepository(db)
        self.execs = RuleExecutionRepository(db)
        self.devices = DeviceRepository(db)
        self.readings = ReadingRepository(db)
        self.device_service = DeviceService(db)
        self.optimizer = OptimizationService(db)
        self.tariffs = TariffService(db)

    # ----------------------------------------------------------- CRUD
    def list_for_home(self, home_id: int) -> list[Rule]:
        return self.rules.by_home(home_id)

    def get_or_404(self, rule_id: int, home_id: int) -> Rule:
        rule = self.db.get(Rule, rule_id)
        if rule is None or rule.home_id != home_id:
            raise NotFoundError(f"Rule {rule_id} not found")
        return rule

    def create(
        self, home_id: int, user_id: int | None, data, source: RuleSource = RuleSource.USER
    ) -> Rule:
        when = data.when_.model_dump(exclude_none=True)
        then = data.then.model_dump()
        until = data.until.model_dump(exclude_none=True) if data.until else None
        device = self._device_or_404(data.device_id, home_id)

        validation = self.validate(home_id, data.device_id, when, then, until)
        if not validation.valid:
            raise ValidationError("; ".join(validation.errors))

        rule = Rule(
            home_id=home_id, device_id=device.id, name=data.name,
            enabled=data.enabled, auto_apply=data.auto_apply, priority=data.priority,
            when_json=when, then_json=then, until_json=until, source=source,
            created_by=user_id,
            estimated_monthly_saving_vnd=validation.estimated_monthly_saving_vnd,
            baseline_snapshot={"baseline_kwh_day": self.optimizer.baseline_daily_kwh(device.id)},
        )
        self.rules.add(rule)
        self.db.commit()
        return rule

    def update(self, rule_id: int, home_id: int, data) -> Rule:
        rule = self.get_or_404(rule_id, home_id)
        if data.name is not None:
            rule.name = data.name
        if data.enabled is not None:
            rule.enabled = data.enabled
        if data.auto_apply is not None:
            rule.auto_apply = data.auto_apply
        if data.priority is not None:
            rule.priority = data.priority

        # Validate structural (when/then/until) edits before persisting, mirroring
        # create(), so an edit cannot store an action outside the capability schema.
        structural = data.when_ is not None or data.then is not None or data.until is not None
        new_when = data.when_.model_dump(exclude_none=True) if data.when_ is not None else rule.when_json
        new_then = data.then.model_dump() if data.then is not None else rule.then_json
        new_until = (
            data.until.model_dump(exclude_none=True) if data.until is not None else rule.until_json
        )
        if structural:
            validation = self.validate(home_id, rule.device_id, new_when, new_then, new_until)
            if not validation.valid:
                raise ValidationError("; ".join(validation.errors))
            rule.when_json, rule.then_json, rule.until_json = new_when, new_then, new_until

        # Re-estimate after edits.
        device = self.devices.get(rule.device_id)
        rule.estimated_monthly_saving_vnd = self.optimizer.estimate_value_vnd(
            device, rule.when_json, rule.then_json, rule.until_json
        )
        self.db.commit()
        return rule

    def delete(self, rule_id: int, home_id: int) -> None:
        rule = self.get_or_404(rule_id, home_id)
        # Business Rule: deleting a rule must NOT delete its execution history.
        self.db.delete(rule)
        self.db.commit()

    def executions(self, rule_id: int, home_id: int) -> list[RuleExecution]:
        self.get_or_404(rule_id, home_id)
        return self.execs.by_rule(rule_id)

    # ----------------------------------------------------------- validation
    def validate(self, home_id: int, device_id: int, when: dict, then: dict, until: dict | None):
        from ..schemas.rule import ConflictItem, RuleValidationOut

        errors: list[str] = []
        warnings: list[str] = []
        device = self.devices.in_home(device_id, home_id)
        if device is None:
            return RuleValidationOut(valid=False, errors=[f"Device {device_id} not in your home"])

        # REQ-4.3.2: action must be allowed by the device capability schema.
        control, value = then.get("control"), then.get("value")
        result = validate_command(DeviceType(device.type), control, value)
        if not result.ok:
            errors.append(f"Action invalid: {result.error}")

        errors.extend(self._validate_condition(home_id, when))
        if until:
            errors.extend(self._validate_condition(home_id, until))

        # NFR-SAF-3: warnings for temperature / safety-critical / unattended power-off.
        schema = get_capability(DeviceType(device.type))
        ctrl_def = schema.control(control) if control else None
        if ctrl_def and ctrl_def.safety_sensitive:
            warnings.append("This rule changes a temperature setting; verify comfort/safety.")
        if device.safety_critical:
            warnings.append("Target device is safety-critical; auto power-off is blocked (NFR-SAF-2).")
        if control == "power" and str(value).lower() == "off":
            warnings.append("This rule powers a device off unattended; confirm nothing depends on it.")

        conflicts = self._detect_conflicts(home_id, device_id, when, then, exclude_rule_id=None)

        estimate = 0.0
        summary = ""
        if not errors:
            est = self.optimizer.estimate_rule(device, when, then, until)
            estimate = est.saved_vnd_month
            summary = self.summarize(device, when, then, until)

        return RuleValidationOut(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            conflicts=[ConflictItem(rule_id=c[0], rule_name=c[1], reason=c[2]) for c in conflicts],
            estimated_monthly_saving_vnd=estimate,
            summary=summary,
        )

    def _validate_condition(self, home_id: int, cond: dict) -> list[str]:
        errors: list[str] = []
        ctype = cond.get("type")
        if ctype not in {"time", "day", "occupancy", "device_state", "tariff_window"}:
            return [f"Unknown condition type '{ctype}'"]
        if ctype == "time" and not cond.get("at") and not cond.get("between"):
            errors.append("Time condition needs 'at' or 'between'")
        if ctype == "day" and not cond.get("days"):
            errors.append("Day condition needs 'days'")
        if ctype in ("occupancy", "device_state"):
            ref_id = cond.get("device_id")
            if ref_id and self.devices.in_home(ref_id, home_id) is None:
                errors.append(f"Condition references device {ref_id} not in your home")
        return errors

    def _detect_conflicts(
        self, home_id: int, device_id: int, when: dict, then: dict, exclude_rule_id: int | None
    ) -> list[tuple[int, str, str]]:
        """REQ-4.3.3: two enabled rules sending different commands to the same
        device at an overlapping time."""
        conflicts: list[tuple[int, str, str]] = []
        control, value = then.get("control"), then.get("value")
        for other in self.rules.enabled_by_home(home_id):
            if other.device_id != device_id or other.id == exclude_rule_id:
                continue
            o_then = other.then_json
            if o_then.get("control") != control:
                continue
            if str(o_then.get("value")) == str(value):
                continue  # same command -> not a conflict
            if self._times_overlap(when, other.when_json):
                conflicts.append(
                    (other.id, other.name,
                     f"Rule '{other.name}' sets {control}={o_then.get('value')} on the same device "
                     f"at an overlapping time")
                )
        return conflicts

    # ----------------------------------------------------------- evaluation
    def evaluate(self, rule: Rule, ts: datetime | None = None) -> bool:
        ts = ts or now()
        return self._condition_holds(rule.when_json, rule.device_id, ts)

    def _condition_holds(self, cond: dict, default_device_id: int, ts: datetime) -> bool:
        ctype = cond.get("type")
        if ctype == "time":
            if cond.get("at"):
                h, m = map(int, cond["at"].split(":"))
                return ts.hour == h and ts.minute == m
            if cond.get("between"):
                a, b = cond["between"]
                return self._in_window(a, b, ts)
            return False
        if ctype == "day":
            return _DAYS[ts.weekday()] in [d.lower() for d in cond.get("days", [])]
        if ctype == "tariff_window":
            tariff = self.tariffs.active(self._home_of(default_device_id))
            return self.tariffs.current_window(tariff, ts) == cond.get("window")
        if ctype == "occupancy":
            dev_id = cond.get("device_id")
            want = cond.get("value")
            want = False if str(want).lower() == "false" else bool(want)
            for_minutes = cond.get("for_minutes")
            if for_minutes:
                window_start = ts - timedelta(minutes=for_minutes)
                rs = self.readings.in_range(dev_id, window_start, ts)
                occ = [r.occupancy for r in rs if r.occupancy is not None]
                return bool(occ) and all(o == want for o in occ)
            latest = self.readings.latest_for_device(dev_id)
            return latest is not None and latest.occupancy == want
        if ctype == "device_state":
            dev_id = cond.get("device_id", default_device_id)
            dev = self.devices.get(dev_id)
            if dev is None:
                return False
            actual = (dev.state or {}).get(cond.get("control"))
            return self._compare(actual, cond.get("op", "eq"), cond.get("value"))
        return False

    # ----------------------------------------------------------- execution
    def execute(self, rule: Rule, initiator: Initiator = Initiator.SCHEDULER) -> RuleExecution | None:
        device = self.devices.get(rule.device_id)
        if device is None:
            return None
        control = rule.then_json.get("control")
        value = rule.then_json.get("value")

        # Idempotency: skip if device already in the desired state.
        if str((device.state or {}).get(control)) == str(value):
            return None
        # Cooldown to avoid rapid re-fire.
        if rule.last_fired_at and (now() - rule.last_fired_at) < timedelta(seconds=_FIRE_COOLDOWN_SECONDS):
            return None

        prior_state = {k: v for k, v in (device.state or {}).items() if k != "power_w"}
        schema = get_capability(DeviceType(device.type))

        if rule.auto_apply:
            result = self.device_service.apply_command(device, control, value, initiator)
            outcome = result.outcome
            detail = result.detail
        else:
            # REQ-4.3.6: auto-action off -> notify only, do not change the device.
            outcome = CommandOutcome.SKIPPED
            detail = "Auto-action disabled: user notified instead of applying."

        execution = self.execs.add(
            RuleExecution(
                rule_id=rule.id, device_id=device.id, ts=now(),
                action_json={"control": control, "value": value},
                initiator=initiator, outcome=outcome, detail=detail,
                prior_state=prior_state,
                undo_deadline=(
                    now() + timedelta(seconds=settings.undo_window_seconds)
                    if outcome == CommandOutcome.SUCCESS and schema.reversible else None
                ),
            )
        )
        rule.last_fired_at = now()
        self.db.commit()

        verb = "applied" if outcome == CommandOutcome.SUCCESS else (
            "suggested" if outcome == CommandOutcome.SKIPPED else outcome.value
        )
        bus.publish(
            EventType.RULE_FIRED,
            {
                "home_id": rule.home_id, "rule_id": rule.id, "execution_id": execution.id,
                "title": f"Rule '{rule.name}' {verb}",
                "body": self.summarize(device, rule.when_json, rule.then_json, rule.until_json),
            },
        )
        return execution

    def undo(self, execution_id: int, home_id: int) -> RuleExecution:
        execution = self.db.get(RuleExecution, execution_id)
        if execution is None:
            raise NotFoundError("Execution not found")
        rule = self.db.get(Rule, execution.rule_id)
        if rule is None or rule.home_id != home_id:
            raise NotFoundError("Execution not found")
        if execution.undone:
            raise ConflictError("Already undone")
        if execution.undo_deadline is None or now() > execution.undo_deadline:
            raise ConflictError("Undo window has expired")
        device = self.devices.get(execution.device_id)
        control = execution.action_json.get("control")
        prior_value = (execution.prior_state or {}).get(control)
        if device is not None and prior_value is not None:
            from ..adapters.devices import get_adapter

            device.state = get_adapter(DeviceType(device.type)).apply_control(
                dict(device.state or {}), control, prior_value
            )
            device.last_seen_at = now()
        execution.undone = True
        self.db.commit()
        return execution

    # ----------------------------------------------------------- summaries
    def summarize(self, device: Device, when: dict, then: dict, until: dict | None = None) -> str:
        text = f"WHEN {self._cond_text(when)} THEN {self._action_text(device, then)}"
        if until:
            text += f" UNTIL {self._cond_text(until)}"
        return text

    def _cond_text(self, cond: dict) -> str:
        ctype = cond.get("type")
        if ctype == "time":
            if cond.get("at"):
                return f"the time is {cond['at']}"
            if cond.get("between"):
                return f"the time is between {cond['between'][0]} and {cond['between'][1]}"
        if ctype == "day":
            return "the day is " + ", ".join(d.capitalize() for d in cond.get("days", []))
        if ctype == "occupancy":
            want = str(cond.get("value")).lower()
            state = "empty" if want == "false" else "occupied"
            mins = f" for {cond['for_minutes']} min" if cond.get("for_minutes") else ""
            return f"the room is {state}{mins}"
        if ctype == "device_state":
            return f"device {cond.get('device_id')} {cond.get('control')} {cond.get('op','is')} {cond.get('value')}"
        if ctype == "tariff_window":
            return f"the tariff is in the {cond.get('window')} window"
        return "the condition holds"

    def _action_text(self, device: Device, then: dict) -> str:
        control, value = then.get("control"), then.get("value")
        name = device.name if device else "the device"
        if control == "power":
            return f"turn {str(value).lower()} {name}"
        if control == "brightness":
            return f"set {name} brightness to {int(float(value))}%"
        if control == "target":
            return f"set {name} temperature to {int(float(value))}°C"
        if control == "speed":
            return f"set {name} fan speed to {int(float(value))}"
        if control == "mode":
            return f"set {name} mode to {value}"
        return f"set {name} {control} to {value}"

    # ----------------------------------------------------------- helpers
    def _device_or_404(self, device_id: int, home_id: int) -> Device:
        device = self.devices.in_home(device_id, home_id)
        if device is None:
            raise NotFoundError(f"Device {device_id} not found")
        return device

    def _home_of(self, device_id: int) -> int:
        dev = self.devices.get(device_id)
        return dev.home_id if dev else 0

    @staticmethod
    def _compare(actual: Any, op: str, value: Any) -> bool:
        try:
            if op in ("gt", "lt", "ge", "le"):
                a, v = float(actual), float(value)
                return {"gt": a > v, "lt": a < v, "ge": a >= v, "le": a <= v}[op]
        except (TypeError, ValueError):
            return False
        if op == "ne":
            return str(actual) != str(value)
        return str(actual) == str(value)

    @staticmethod
    def _in_window(start: str, end: str, ts: datetime) -> bool:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        s, e, cur = time(sh, sm), time(eh, em), ts.time()
        if s <= e:
            return s <= cur < e
        return cur >= s or cur < e

    def _times_overlap(self, c1: dict, c2: dict) -> bool:
        if c1.get("type") != "time" or c2.get("type") != "time":
            # Non-time conditions: treat as potentially overlapping (conservative).
            return True
        h1 = self._hours_of(c1)
        h2 = self._hours_of(c2)
        return bool(h1 & h2)

    @staticmethod
    def _hours_of(cond: dict) -> set[int]:
        from ..core.timeutil import hour_set_from_window

        if cond.get("at"):
            return {int(cond["at"].split(":")[0])}
        if cond.get("between"):
            return hour_set_from_window(cond["between"][0], cond["between"][1])
        return set(range(24))
