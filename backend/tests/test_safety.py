"""Safety requirements (NFR-SAF-1..3)."""
from tests.conftest import device_of


def test_ac_compressor_rate_limit(client, dev_headers, devices):
    # NFR-SAF-1: <= 1 AC compressor command per 3 minutes.
    from app.database import SessionLocal
    from app.domain.models import Device

    ac = device_of(devices, "ac")
    # Clear any prior compressor-command timestamp for a deterministic check.
    db = SessionLocal()
    try:
        d = db.get(Device, ac["id"])
        state = dict(d.state or {})
        state.pop("last_ac_cmd_ts", None)
        state["forced_offline"] = False
        d.state = state
        d.online = True
        db.commit()
    finally:
        db.close()

    first = client.post(f"/api/devices/{ac['id']}/command", headers=dev_headers,
                        json={"control": "target", "value": 24}).json()
    assert first["outcome"] == "success"
    second = client.post(f"/api/devices/{ac['id']}/command", headers=dev_headers,
                         json={"control": "target", "value": 25}).json()
    assert second["outcome"] == "rejected"
    assert "rate limit" in second["detail"].lower()


def test_safety_critical_device_not_auto_powered_off(client, devices):
    # NFR-SAF-2: a rule/auto-action must not power off a safety-critical device.
    from app.database import SessionLocal
    from app.domain.enums import CommandOutcome, Initiator
    from app.domain.models import Device
    from app.services.device_service import DeviceService

    fridge = next(d for d in devices if d["safety_critical"])
    db = SessionLocal()
    try:
        device = db.get(Device, fridge["id"])
        result = DeviceService(db).apply_command(device, "power", "off", Initiator.SCHEDULER)
        assert result.outcome == CommandOutcome.SKIPPED
        assert "safety-critical" in result.detail.lower()
    finally:
        db.close()


def test_safety_warnings_on_validation(client, dev_headers, devices):
    # NFR-SAF-3: warn on temperature change, safety-critical, unattended power-off.
    ac = device_of(devices, "ac")
    temp_rule = client.post("/api/rules/validate", headers=dev_headers, json={
        "name": "temp", "device_id": ac["id"],
        "when": {"type": "time", "at": "22:00"},
        "then": {"control": "target", "value": 20}}).json()
    assert any("temperature" in w.lower() for w in temp_rule["warnings"])

    fridge = next(d for d in devices if d["safety_critical"])
    off_rule = client.post("/api/rules/validate", headers=dev_headers, json={
        "name": "fridge off", "device_id": fridge["id"],
        "when": {"type": "time", "at": "03:00"},
        "then": {"control": "power", "value": "off"}}).json()
    assert any("safety-critical" in w.lower() for w in off_rule["warnings"])


def test_safety_critical_device_cannot_be_forced_offline(client, dev_headers, devices):
    # NFR-SAF: the safety-critical fridge must always remain reachable (cannot be forced offline).
    fridge = next(d for d in devices if d["safety_critical"])
    res = client.post(f"/api/devices/{fridge['id']}/connectivity?online=false", headers=dev_headers)
    assert res.status_code == 409
