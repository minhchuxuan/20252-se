"""Real-time monitoring & reporting (REQ-4.1.1..4.1.5, 6.1 export)."""


def test_dashboard_reports_home_metrics(client, dev_headers):
    dash = client.get("/api/dashboard", headers=dev_headers).json()
    # REQ-4.1.1/4.1.2: power + cumulative kWh + estimated bill present.
    for key in ("home_total_w", "kwh_today", "kwh_cycle", "estimated_bill_vnd",
                "savings_cycle_vnd", "devices"):
        assert key in dash
    assert dash["total_devices"] == 6
    assert dash["currency"] == "VND"
    assert dash["kwh_cycle"] >= dash["kwh_today"] >= 0


def test_top_consumers_ranked(client, dev_headers):
    # REQ-4.1.5: top consuming devices.
    top = client.get("/api/top-consumers?range=week&limit=3", headers=dev_headers).json()
    assert 1 <= len(top) <= 3
    kwhs = [t["kwh"] for t in top]
    assert kwhs == sorted(kwhs, reverse=True)
    assert all("cost_vnd" in t and "share_pct" in t for t in top)


def test_consumption_series_buckets(client, dev_headers):
    series = client.get("/api/consumption?range=week", headers=dev_headers).json()
    assert series["granularity"] == "day"
    assert series["total_kwh"] >= 0
    assert all("kwh" in p and "cost_vnd" in p for p in series["points"])


def test_consumption_rejects_foreign_device(client, resident_headers, devices):
    # NFR-SEC-4: a Resident must NOT read another unit's device readings by passing a
    # foreign device_id (cross-unit IDOR regression).
    foreign_device = devices[0]["id"]  # belongs to another unit, not the resident's
    res = client.get(f"/api/consumption?range=week&device_id={foreign_device}", headers=resident_headers)
    assert res.status_code == 404


def test_csv_export(client, dev_headers):
    # 6.1 Data export.
    res = client.get("/api/reports/export/readings.csv?days=2", headers=dev_headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert res.text.splitlines()[0].startswith("device_id,device_name,timestamp")
