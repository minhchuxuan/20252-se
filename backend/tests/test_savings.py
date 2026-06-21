"""Optimization Engine & bill-saving estimation (REQ-4.5.1..4.5.5)."""
import pytest

from tests.conftest import device_of


def test_estimate_before_save_uses_srs_formula(client, dev_headers, devices):
    # REQ-4.5.2/4.5.3: estimate shown before saving, computed as
    # sum((baseline_kWh - expected_kWh_with_rule) * tariff_VND_per_kWh).
    plug = device_of(devices, "plug")
    body = {"name": "overnight", "device_id": plug["id"],
            "when": {"type": "time", "between": ["00:00", "06:00"]},
            "then": {"control": "power", "value": "off"}}
    est = client.post("/api/savings/estimate", headers=dev_headers, json=body).json()
    assert est["baseline_kwh_month"] > 0           # REQ-4.5.1 baseline exists
    assert est["expected_kwh_month"] == 0          # device off in window
    assert est["saved_kwh_month"] == pytest.approx(
        est["baseline_kwh_month"] - est["expected_kwh_month"], rel=1e-6
    )
    assert est["saved_vnd_month"] == pytest.approx(
        est["saved_kwh_month"] * est["tariff_vnd_per_kwh"], rel=0.02
    )
    assert est["explanation"]


def test_raising_ac_target_saves_energy(client, dev_headers, devices):
    ac = device_of(devices, "ac")
    body = {"name": "warmer ac", "device_id": ac["id"],
            "when": {"type": "time", "between": ["22:00", "06:00"]},
            "then": {"control": "target", "value": 28}}
    est = client.post("/api/savings/estimate", headers=dev_headers, json=body).json()
    assert est["saved_kwh_month"] > 0
    assert est["expected_kwh_month"] < est["baseline_kwh_month"]


def test_savings_summary_reports_cycle(client, dev_headers):
    # REQ-4.5.4: savings so far in the current billing cycle.
    summ = client.get("/api/savings/summary", headers=dev_headers).json()
    assert summ["currency"] == "VND"
    assert summ["saved_vnd_cycle"] >= 0
    assert summ["estimated_saved_vnd_month"] >= 0
    assert summ["cycle_start"] < summ["cycle_end"]


def test_savings_records_present(client, dev_headers):
    records = client.get("/api/savings/records", headers=dev_headers).json()
    # Seed creates a measured record for the active overnight rule.
    assert any(r["kind"] == "measured" for r in records)


def test_drift_check_is_reachable(client, dev_headers):
    # REQ-4.5.5: check_drift compares measured vs estimated saving and flags a
    # rule when they diverge by more than ±20%.
    from app.database import SessionLocal
    from app.services.optimization_service import OptimizationService

    rules = client.get("/api/rules", headers=dev_headers).json()
    rule = next((r for r in rules if r["estimated_monthly_saving_vnd"] > 0), None)
    assert rule is not None
    db = SessionLocal()
    try:
        flagged = OptimizationService(db).check_drift(rule["id"])
        assert isinstance(flagged, bool)
    finally:
        db.close()
