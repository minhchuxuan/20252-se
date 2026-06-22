"""Unit tests for pure domain logic (no HTTP, no DB).

Black-box techniques: equivalence partitioning + boundary-value analysis on the
capability validator (SE Intro 15), plus tariff math and the simulator.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.capability import get_capability, validate_command
from app.domain.enums import DeviceType, TariffType
from app.core.timeutil import current_billing_cycle, hour_set_from_window


# --- REQ-4.2.3 command validation: boundary-value analysis (15/16, 30/31) plus the
# non-numeric path together cover every branch of the AC target guard (16..30). ---
@pytest.mark.parametrize(
    "value,ok",
    [(16, True), (30, True), (23, True), (15, False), (31, False), ("hot", False)],
)
def test_ac_target_boundaries(value, ok):
    assert validate_command(DeviceType.AC, "target", value).ok is ok


def test_validate_rejects_unknown_control():
    r = validate_command(DeviceType.PLUG, "brightness", 50)
    assert not r.ok and "no control" in r.error


def test_validate_enum_and_toggle():
    assert validate_command(DeviceType.FAN, "mode", "sleep").ok
    assert not validate_command(DeviceType.FAN, "mode", "turbo").ok
    assert validate_command(DeviceType.PLUG, "power", "on").ok
    assert not validate_command(DeviceType.PLUG, "power", "maybe").ok


def test_sensor_is_readonly():
    assert get_capability(DeviceType.SENSOR).controls == ()


# --- tariff pricing (flat + tiered integration) ---
def test_flat_tariff_pricing():
    from app.services.tariff_service import TariffService
    from app.domain.models import Tariff

    svc = TariffService.__new__(TariffService)  # no DB needed for pure pricing
    t = Tariff(type=TariffType.FLAT, config={"price": 2000}, currency="VND")
    assert svc.effective_price(t) == 2000
    assert svc.price_energy(t, 10) == 20000


def test_tiered_tariff_is_progressive():
    from app.services.tariff_service import TariffService
    from app.domain.models import Tariff

    svc = TariffService.__new__(TariffService)
    tiers = {"tiers": [{"up_to_kwh": 50, "price": 1000}, {"up_to_kwh": None, "price": 3000}]}
    t = Tariff(type=TariffType.TIERED, config=tiers, currency="VND")
    # First 50 kWh @1000, next 50 @3000 = 50000 + 150000.
    assert svc.price_energy(t, 100, monthly_kwh_before=0) == pytest.approx(200000)
    # Marginal price above 50 kWh is the top tier.
    assert svc.effective_price(t, monthly_kwh=120) == 3000


def test_billing_cycle_contains_now():
    # Branch coverage of the cycle-start decision (ts >= this_month_start?).
    # True branch: the timestamp is on/after the billing day -> cycle starts this month.
    ts = datetime(2026, 6, 15, 8, tzinfo=timezone.utc)
    start, end = current_billing_cycle(ts, billing_day=1)
    assert start <= ts < end
    assert start.day == 1 and end.month == 7
    # False branch: the timestamp is before the billing day -> cycle started last month.
    start2, end2 = current_billing_cycle(datetime(2026, 6, 3, tzinfo=timezone.utc), billing_day=15)
    assert start2.month == 5 and start2.day == 15
    assert end2.month == 6 and end2.day == 15


def test_hour_set_wraps_midnight():
    # Branch coverage of the window function's three branches.
    assert hour_set_from_window("22:00", "04:00") == {22, 23, 0, 1, 2, 3}  # wraps midnight
    assert hour_set_from_window("08:00", "12:00") == {8, 9, 10, 11}        # same-day window
    assert hour_set_from_window("00:00", "00:00") == set(range(24))        # empty == full day


# --- simulator: AC consumes more at a lower target (drives "AC too cold") ---
def test_simulator_ac_savings_differential():
    from app.simulator.engine import generate_history
    from app.adapters.devices import get_adapter

    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    ad = get_adapter(DeviceType.AC)
    _, _, k24 = generate_history(DeviceType.AC, ad.default_state(), start, end, 900,
                                 lambda ts, s: {"power": "on", "target": 24, "mode": "cool"})
    _, _, k26 = generate_history(DeviceType.AC, ad.default_state(), start, end, 900,
                                 lambda ts, s: {"power": "on", "target": 26, "mode": "cool"})
    assert k24 > k26 > 0  # raising the target saves energy


def test_password_hash_roundtrip_never_plaintext():
    # NFR-SEC-3
    from app.core.security import hash_password, verify_password

    h = hash_password("s3cret-pw")
    assert "s3cret-pw" not in h
    assert verify_password("s3cret-pw", h)
    assert not verify_password("wrong", h)
