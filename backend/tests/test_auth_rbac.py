"""Authentication & role-based authorization (NFR-SEC-2, Business Rule:
only the Administrator manages residents/devices)."""


def test_login_returns_token_and_user(client):
    res = client.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo1234"})
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer" and body["user"]["role"] == "admin"


def test_login_rejects_bad_password(client):
    res = client.post("/api/auth/login", json={"email": "admin@demo.com", "password": "nope"})
    assert res.status_code == 401


def test_unauthenticated_request_is_rejected(client):
    assert client.get("/api/dashboard").status_code == 401


def test_me_returns_current_user(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers).json()
    assert me["email"] == "admin@demo.com"


def test_resident_cannot_add_device(client, resident_headers):
    # Only Administrator/Developer may add devices.
    res = client.post("/api/devices", headers=resident_headers,
                      json={"name": "X", "type": "plug", "room": "X"})
    assert res.status_code == 403


def test_resident_cannot_create_tariff(client, resident_headers):
    res = client.post("/api/tariffs", headers=resident_headers,
                      json={"name": "x", "type": "flat", "config": {"price": 1}})
    assert res.status_code == 403


def test_admin_can_onboard_resident(client, admin_headers, devices):
    # The Administrator sells a new unit: it ships with the default device package and
    # the new Resident controls every operable device in their own unit (BR / RBAC).
    res = client.post("/api/auth/residents", headers=admin_headers, json={
        "email": "tenant3@demo.com", "full_name": "Tenant 3", "password": "demo1234",
        "unit_name": "Unit 103",
    })
    assert res.status_code == 201, res.text
    login = client.post("/api/auth/login", json={"email": "tenant3@demo.com", "password": "demo1234"})
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    my_devices = client.get("/api/devices", headers=h).json()
    assert len(my_devices) >= 5  # the default package
    bulb = next(d for d in my_devices if d["type"] == "bulb")
    ok = client.post(f"/api/devices/{bulb['id']}/command", headers=h,
                     json={"control": "power", "value": "on"})
    assert ok.status_code == 200 and ok.json()["outcome"] == "success"
    # NFR-SEC-4: the new Resident cannot reach a device in another unit.
    other = next(d for d in devices if d["type"] == "fan")
    denied = client.post(f"/api/devices/{other['id']}/command", headers=h,
                         json={"control": "power", "value": "on"})
    assert denied.status_code == 404


def test_admin_cannot_control_device(client, admin_headers, devices):
    # The Administrator (apartment owner) views only — never operates devices (NFR-SEC-2).
    fan = next(d for d in devices if d["type"] == "fan")
    res = client.post(f"/api/devices/{fan['id']}/command", headers=admin_headers,
                      json={"control": "power", "value": "on"})
    assert res.status_code == 403
