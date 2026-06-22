"""Administrator (building owner) oversight across units (NFR-SEC-2)."""


def test_admin_building_overview(client, admin_headers):
    # The building owner sees a roster + per-unit metrics + building totals.
    ov = client.get("/api/admin/overview", headers=admin_headers).json()
    assert ov["unit_count"] >= 2            # resident units only (maintenance unit excluded)
    assert ov["resident_count"] >= 2
    assert ov["currency"] == "VND"
    assert ov["estimated_bill_vnd"] >= 0
    assert len(ov["units"]) == ov["unit_count"]
    # The Developer's maintenance unit is not a household and must not appear.
    assert all(u["resident_email"] != "dev@demo.com" for u in ov["units"])
    a_unit = ov["units"][0]
    for key in ("home_id", "unit_name", "total_w", "kwh_cycle", "estimated_bill_vnd",
                "online_devices", "total_devices"):
        assert key in a_unit


def test_admin_can_drill_into_a_unit(client, admin_headers):
    ov = client.get("/api/admin/overview", headers=admin_headers).json()
    home_id = ov["units"][0]["home_id"]
    dash = client.get(f"/api/admin/units/{home_id}/dashboard", headers=admin_headers).json()
    assert dash["total_devices"] == 6
    devices = client.get(f"/api/admin/units/{home_id}/devices", headers=admin_headers).json()
    assert len(devices) == 6


def test_resident_cannot_access_building_overview(client, resident_headers):
    # NFR-SEC-2: oversight is the Administrator's privilege only.
    assert client.get("/api/admin/overview", headers=resident_headers).status_code == 403


def test_admin_has_no_unit(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers).json()
    assert me["role"] == "admin"
    assert me["home_id"] is None


def test_admin_cannot_add_device(client, admin_headers):
    # The Administrator owns no unit; adding an ad-hoc device must fail cleanly (403),
    # not crash on a NULL home_id. Devices are provisioned when a unit is sold.
    res = client.post("/api/devices", headers=admin_headers,
                      json={"name": "X", "type": "plug", "room": "Y"})
    assert res.status_code == 403


def _sell_unit(client, admin_headers, email, unit_name):
    res = client.post("/api/auth/residents", headers=admin_headers, json={
        "email": email, "full_name": "Temp Tenant",
        "password": "demo1234", "unit_name": unit_name,
    })
    assert res.status_code == 201, res.text
    return res.json()["home_id"]


def test_admin_offboard_resident_is_soft(client, admin_headers):
    # Onboard a throwaway unit (shared DB) so we don't disturb the seeded residents.
    home_id = _sell_unit(client, admin_headers, "offboard-me@demo.com", "Unit 991")
    # It carries the default package and the tenant can authenticate.
    assert client.post("/api/auth/login", json={
        "email": "offboard-me@demo.com", "password": "demo1234"}).status_code == 200
    assert len(client.get(f"/api/admin/units/{home_id}/devices", headers=admin_headers).json()) == 6

    # Soft offboard: 204, then the account can no longer authenticate (NFR-SEC-2).
    assert client.delete(f"/api/admin/units/{home_id}/resident", headers=admin_headers).status_code == 204
    assert client.post("/api/auth/login", json={
        "email": "offboard-me@demo.com", "password": "demo1234"}).status_code == 401

    # The unit survives as vacant inventory; its devices/history are retained.
    ov = client.get("/api/admin/overview", headers=admin_headers).json()
    unit = next(u for u in ov["units"] if u["home_id"] == home_id)
    assert unit["resident_email"] is None and unit["resident_name"] is None
    assert len(client.get(f"/api/admin/units/{home_id}/devices", headers=admin_headers).json()) == 6


def test_offboard_vacant_unit_is_conflict(client, admin_headers):
    home_id = _sell_unit(client, admin_headers, "offboard-twice@demo.com", "Unit 992")
    assert client.delete(f"/api/admin/units/{home_id}/resident", headers=admin_headers).status_code == 204
    # No resident left to remove.
    assert client.delete(f"/api/admin/units/{home_id}/resident", headers=admin_headers).status_code == 409


def test_resident_cannot_offboard(client, resident_headers):
    # NFR-SEC-2: only the Administrator manages the resident lifecycle.
    assert client.delete("/api/admin/units/1/resident", headers=resident_headers).status_code == 403
