"""Device capability schema & control (REQ-4.2.1..4.2.5)."""
import pytest

from tests.conftest import device_of


def test_capability_endpoint_drives_controls(client, dev_headers, devices):
    # REQ-4.2.1: controls are obtained from the capability schema.
    ac = device_of(devices, "ac")
    cap = client.get(f"/api/devices/{ac['id']}/capabilities", headers=dev_headers).json()
    names = {c["name"] for c in cap["controls"]}
    assert names == {"power", "target", "mode"}
    target = next(c for c in cap["controls"] if c["name"] == "target")
    assert target["kind"] == "range" and target["min"] == 16 and target["max"] == 30


def test_mock_profiles_available(client, dev_headers):
    # REQ-4.2.5: at least plug, bulb, fan, AC, occupancy sensor profiles.
    profiles = client.get("/api/devices/profiles/mock", headers=dev_headers).json()
    types = {p["type"] for p in profiles}
    assert {"plug", "bulb", "fan", "ac", "sensor"} <= types


def test_command_validation_rejects_out_of_range(client, dev_headers, devices):
    # REQ-4.2.3/4.2.4 (driven through the developer/maintainer role).
    ac = device_of(devices, "ac")
    ok = client.post(f"/api/devices/{ac['id']}/command", headers=dev_headers,
                     json={"control": "target", "value": 25})
    assert ok.json()["outcome"] == "success"
    bad = client.post(f"/api/devices/{ac['id']}/command", headers=dev_headers,
                      json={"control": "target", "value": 99})
    assert bad.json()["outcome"] == "rejected"


def test_offline_device_command_times_out(client, dev_headers, devices):
    # REQ-4.1.4 offline detection + REQ-4.2.4 timeout on unreachable device.
    fan = device_of(devices, "fan")
    client.post(f"/api/devices/{fan['id']}/connectivity?online=false", headers=dev_headers)
    res = client.post(f"/api/devices/{fan['id']}/command", headers=dev_headers,
                      json={"control": "power", "value": "on"}).json()
    assert res["outcome"] == "timeout"
    # Dashboard marks it unreachable.
    dash = client.get("/api/dashboard", headers=dev_headers).json()
    fan_live = next(d for d in dash["devices"] if d["device_id"] == fan["id"])
    assert fan_live["online"] is False
    # Bring it back online for other tests.
    client.post(f"/api/devices/{fan['id']}/connectivity?online=true", headers=dev_headers)


@pytest.mark.parametrize("dtype", ["plug", "bulb", "fan", "ac"])
def test_power_on_off_control(client, dev_headers, devices, dtype):
    # REQ-4.2.2: on/off control for plug, bulb, fan and AC.
    from app.database import SessionLocal
    from app.domain.models import Device

    dev = device_of(devices, dtype)
    client.post(f"/api/devices/{dev['id']}/connectivity?online=true", headers=dev_headers)
    if dtype == "ac":  # clear the compressor rate-limit timer for determinism
        db = SessionLocal()
        try:
            d = db.get(Device, dev["id"])
            s = dict(d.state or {})
            s.pop("last_ac_cmd_ts", None)
            d.state = s
            db.commit()
        finally:
            db.close()
    res = client.post(f"/api/devices/{dev['id']}/command", headers=dev_headers,
                      json={"control": "power", "value": "on"}).json()
    assert res["outcome"] == "success"
    assert res["state"]["power"] == "on"


def test_add_and_delete_mock_device(client, dev_headers):
    created = client.post("/api/devices", headers=dev_headers,
                          json={"name": "Test Bulb", "type": "bulb", "room": "Lab"})
    assert created.status_code == 201
    did = created.json()["id"]
    cap = client.get(f"/api/devices/{did}/capabilities", headers=dev_headers).json()
    assert any(c["name"] == "brightness" for c in cap["controls"])
    assert client.delete(f"/api/devices/{did}", headers=dev_headers).status_code == 204
