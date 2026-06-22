"""Demo seed data.

Models one apartment building with:

  * one Administrator (building owner) who owns no unit (home_id NULL) and oversees
    every unit, plus a building-wide EVN-style tiered tariff;
  * three units, each a Home occupied by one Resident (or the Developer/tester),
    pre-loaded with the default device package and ~21 days of back-dated telemetry
    containing deliberate, detectable waste patterns:

      - a TV plug left on standby overnight            -> "idle plug" recommendation
      - a hallway light left on while the unit is empty -> "light when empty"
      - a bedroom AC habitually set to 18 °C           -> "AC too cold"
      - a fridge plug (safety-critical) drawing 24/7    -> must NOT be recommended off

Each unit gets one accepted auto-rule with measured cycle savings, and the habit
miner runs per unit, so the system is fully populated and demoable on first launch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from .config import settings
from .core.clock import now
from .core.security import hash_password
from .core.timeutil import current_billing_cycle
from .database import SessionLocal
from .domain.enums import (
    DeviceType,
    NotificationType,
    Role,
    RuleSource,
    SavingsKind,
)
from .domain.models import (
    Device,
    DevicePermission,
    Home,
    Notification,
    Reading,
    Rule,
    SavingsRecord,
    Tariff,
    User,
)
from .services.provisioning import DEFAULT_UNIT_DEVICES
from .adapters.devices import get_adapter
from .domain.capability import get_capability
from .simulator.engine import generate_history

logger = logging.getLogger("sheo.seed")

# EVN-style residential tiered tariff (representative, configurable in Settings).
EVN_TIERS = {
    "tiers": [
        {"up_to_kwh": 50, "price": 1806},
        {"up_to_kwh": 100, "price": 1866},
        {"up_to_kwh": 200, "price": 2167},
        {"up_to_kwh": 300, "price": 2729},
        {"up_to_kwh": 400, "price": 3050},
        {"up_to_kwh": None, "price": 3151},
    ]
}

DEMO_PASSWORD = "demo1234"


# --- behaviour scripts (control state as a function of time) -------------------
def _tv(ts, state):
    return {"power": "on", "load_w": 120.0 if 8 <= ts.hour < 23 else 25.0}


def _hall_light(ts, state):
    # Left on right through the working day (09:00–17:00) when the unit is empty —
    # the classic "forgot to switch it off" waste the habit miner should catch.
    on = 6 <= ts.hour < 23
    return {"power": "on" if on else "off", "brightness": 75}


def _bedroom_ac(ts, state):
    # Habitually set very cold (18°C) overnight while occupants sleep — the
    # "AC too cold" waste the miner flags (raising the target saves a lot).
    on = ts.hour >= 22 or ts.hour < 6
    return {"power": "on", "target": 18, "mode": "cool"} if on else {"power": "off"}


def _fan(ts, state):
    if 11 <= ts.hour < 18 and ts.weekday() < 6:
        return {"power": "on", "speed": 3, "mode": "normal"}
    return {"power": "off", "speed": 0}


def _fridge(ts, state):
    return {"power": "on", "load_w": 120.0}


# Behaviour for each device of the default package, keyed by device name.
_BEHAVIOURS = {
    "Living Room TV Plug": _tv,
    "Hallway Light": _hall_light,
    "Bedroom AC": _bedroom_ac,
    "Living Room Fan": _fan,
    "Kitchen Fridge Plug": _fridge,
    "Living Room Sensor": None,
}

# The units that ship with the building: (unit name, resident email, name, role).
_UNITS = [
    ("Unit 101", "resident@demo.com", "Demo Resident", Role.RESIDENT),
    ("Unit 102", "resident2@demo.com", "Demo Resident 2", Role.RESIDENT),
    ("Unit 100 (Maintenance)", "dev@demo.com", "Demo Developer", Role.DEVELOPER),
]


def run_seed() -> None:
    db = SessionLocal()
    try:
        if db.query(Home).first() is not None or db.query(User).first() is not None:
            logger.info("seed skipped (data already present)")
            return
        logger.info("seeding demo data…")

        # Administrator (building owner): no unit, oversees the whole building.
        db.add(User(
            email="admin@demo.com", full_name="Demo Administrator",
            password_hash=hash_password(DEMO_PASSWORD), role=Role.ADMIN, home_id=None,
        ))
        # Building-wide tariff (home_id NULL) the Administrator manages.
        db.add(Tariff(home_id=None, name="EVN bậc thang (residential)", type="tiered",
                      config=EVN_TIERS, currency="VND", active=True))
        db.commit()

        end = now()
        start = end - timedelta(days=settings.seed_history_days)
        for unit_name, email, full_name, role in _UNITS:
            _seed_unit(db, unit_name, email, full_name, role, start, end)

        logger.info("seed complete")
    finally:
        db.close()


def _seed_unit(
    db, unit_name: str, email: str, full_name: str, role: Role, start: datetime, end: datetime
) -> None:
    """Create one unit (Home) with its occupant, default device package, back-dated
    telemetry, control grants and an accepted saving rule. Habit recommendations are
    NOT pre-generated: they are produced on demand when the resident runs ``analyze``."""
    home = Home(name=unit_name, billing_cycle_day=1, locale="vi")
    db.add(home)
    db.flush()

    occupant = User(email=email, full_name=full_name,
                    password_hash=hash_password(DEMO_PASSWORD), role=role, home_id=home.id)
    db.add(occupant)
    db.flush()

    devices: dict[str, Device] = {}
    for dev_name, room, dtype, safety in DEFAULT_UNIT_DEVICES:
        schema = get_capability(dtype)
        adapter = get_adapter(dtype)
        readings, final_state, kwh = generate_history(
            dtype, adapter.default_state(), start, end, 900, _BEHAVIOURS[dev_name], kwh_start=0.0
        )
        device = Device(
            home_id=home.id, name=dev_name, type=dtype, room=room, online=True,
            state=final_state, kwh_total=kwh, safety_critical=safety,
            capability=schema.to_dict(), is_mock=True, last_seen_at=end,
        )
        db.add(device)
        db.flush()
        devices[dev_name] = device
        db.add_all([Reading(device_id=device.id, **r) for r in readings])
        # The occupant controls every operable device in their own unit; the
        # safety-critical fridge and the read-only sensor are never granted.
        if dtype != DeviceType.SENSOR and not safety:
            db.add(DevicePermission(user_id=occupant.id, device_id=device.id, can_control=True))
    db.commit()

    _seed_accepted_rule_and_savings(db, home, devices["Living Room TV Plug"])
    db.add(Notification(
        home_id=home.id, type=NotificationType.MONTHLY_REPORT,
        title="Welcome to your Smart Home Energy Optimizer",
        body="You have 3 weeks of usage history — open Recommendations and run "
             "“Analyze my usage” to get personalised saving ideas.",
    ))
    db.commit()


def _seed_accepted_rule_and_savings(db, home: Home, tv_plug: Device) -> None:
    """One pre-accepted auto-rule + measured savings already accrued this cycle."""
    from .services.optimization_service import OptimizationService

    optimizer = OptimizationService(db)
    when = {"type": "time", "between": ["00:00", "06:00"]}
    then = {"control": "power", "value": "off"}
    est = optimizer.estimate_rule(tv_plug, when, then)

    rule = Rule(
        home_id=home.id, device_id=tv_plug.id, name="Turn off TV plug overnight",
        enabled=True, auto_apply=True, priority=50, when_json=when, then_json=then,
        source=RuleSource.USER, estimated_monthly_saving_vnd=est.saved_vnd_month,
        baseline_snapshot={"baseline_kwh_day": optimizer.baseline_daily_kwh(tv_plug.id)},
    )
    db.add(rule)
    db.flush()

    # Measured savings so far this cycle = nightly avoided standby × elapsed days.
    cycle_start, cycle_end = current_billing_cycle(now(), home.billing_cycle_day)
    nightly_kwh = optimizer.window_baseline_kwh(tv_plug.id, {0, 1, 2, 3, 4, 5})
    elapsed_days = max(0.0, (now() - cycle_start).total_seconds() / 86400.0)
    saved_kwh = nightly_kwh * elapsed_days
    saved_vnd = optimizer.measured_to_vnd(home.id, saved_kwh)
    db.add(SavingsRecord(
        home_id=home.id, rule_id=rule.id, device_id=tv_plug.id,
        period_start=cycle_start, period_end=now(),
        baseline_kwh=saved_kwh, expected_kwh_with_rule=0.0, actual_kwh=0.0,
        saved_kwh=saved_kwh, saved_vnd=saved_vnd, kind=SavingsKind.MEASURED,
    ))
    db.commit()
