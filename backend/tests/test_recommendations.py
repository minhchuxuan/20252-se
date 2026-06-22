"""Habit learning & recommendations (REQ-4.4.1..4.4.5)."""


def test_recommendations_are_readable_and_explainable(client, dev_headers):
    # Recommendations are produced on demand (the seed no longer pre-generates them).
    client.post("/api/recommendations/analyze", headers=dev_headers)
    recs = client.get("/api/recommendations", headers=dev_headers).json()
    assert len(recs) >= 1
    r = recs[0]
    # REQ-4.4.2: readable WHEN-THEN + the data window used.
    assert "WHEN" in r["summary"] and "THEN" in r["summary"]
    assert r["rationale"]
    assert r["data_window_start"] and r["data_window_end"]
    assert r["estimated_monthly_saving_vnd"] > 0


def test_recommendations_ranked_and_capped(client, dev_headers):
    # REQ-4.4.3: ranked by VND saving, at most five.
    recs = client.post("/api/recommendations/analyze", headers=dev_headers).json()
    vals = [r["estimated_monthly_saving_vnd"] for r in recs]
    assert vals == sorted(vals, reverse=True)
    assert len(recs) <= 5


def test_new_device_without_history_yields_no_recommendation(client, dev_headers):
    # REQ-4.4.1: need >= 7 days of telemetry.
    did = client.post("/api/devices", headers=dev_headers,
                      json={"name": "Fresh Plug", "type": "plug", "room": "Lab"}).json()["id"]
    recs = client.post("/api/recommendations/analyze", headers=dev_headers).json()
    assert all(r["device_id"] != did for r in recs)
    client.delete(f"/api/devices/{did}", headers=dev_headers)


def test_accept_recommendation_becomes_rule(client, dev_headers):
    # REQ-4.4.4: explicit acceptance turns it into a rule.
    recs = client.post("/api/recommendations/analyze", headers=dev_headers).json()
    rec = recs[0]
    res = client.post(f"/api/recommendations/{rec['id']}/accept", headers=dev_headers,
                      json={"auto_apply": False})
    assert res.status_code == 201
    rid = res.json()["id"]
    rules = client.get("/api/rules", headers=dev_headers).json()
    assert any(x["id"] == rid for x in rules)
    # No longer shown as an active recommendation.
    active = client.get("/api/recommendations", headers=dev_headers).json()
    assert all(r["id"] != rec["id"] for r in active)


def test_dismiss_suppresses_recommendation(client, dev_headers):
    # REQ-4.4.5: dismissed -> not shown again for the same device/condition.
    recs = client.post("/api/recommendations/analyze", headers=dev_headers).json()
    assert recs
    rec = recs[-1]
    client.post(f"/api/recommendations/{rec['id']}/dismiss", headers=dev_headers)
    after = client.post("/api/recommendations/analyze", headers=dev_headers).json()
    assert all(r["id"] != rec["id"] for r in after)
