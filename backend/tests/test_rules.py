"""Rules, scheduling, auto-actions, undo (REQ-4.3.1..4.3.6)."""
from tests.conftest import device_of


def test_action_must_match_capability(client, dev_headers, devices):
    # REQ-4.3.2: action limited to capability schema (plug has no brightness).
    plug = device_of(devices, "plug")
    body = {"name": "bad", "device_id": plug["id"],
            "when": {"type": "time", "at": "01:00"},
            "then": {"control": "brightness", "value": 50}}
    val = client.post("/api/rules/validate", headers=dev_headers, json=body).json()
    assert val["valid"] is False
    assert client.post("/api/rules", headers=dev_headers, json=body).status_code == 422


def test_auto_action_off_by_default(client, dev_headers, devices):
    # REQ-4.3.6: auto-action requires explicit opt-in.
    bulb = device_of(devices, "bulb")
    body = {"name": "default rule", "device_id": bulb["id"],
            "when": {"type": "time", "at": "02:00"},
            "then": {"control": "power", "value": "off"}}
    rule = client.post("/api/rules", headers=dev_headers, json=body).json()
    assert rule["auto_apply"] is False
    assert "WHEN" in rule["summary"] and "THEN" in rule["summary"]


def test_conflict_detection(client, dev_headers, devices):
    # REQ-4.3.3: two enabled rules sending different commands to the same device
    # at an overlapping time are flagged.
    fan = device_of(devices, "fan")
    base = {"name": "fan on noon", "device_id": fan["id"],
            "when": {"type": "time", "between": ["12:00", "14:00"]},
            "then": {"control": "power", "value": "on"}}
    client.post("/api/rules", headers=dev_headers, json=base)
    conflicting = {"name": "fan off noon", "device_id": fan["id"],
                   "when": {"type": "time", "between": ["13:00", "15:00"]},
                   "then": {"control": "power", "value": "off"}}
    val = client.post("/api/rules/validate", headers=dev_headers, json=conflicting).json()
    assert len(val["conflicts"]) >= 1


def test_enable_disable_edit_delete(client, dev_headers, devices):
    # REQ-4.3.4
    bulb = device_of(devices, "bulb")
    rid = client.post("/api/rules", headers=dev_headers, json={
        "name": "editable", "device_id": bulb["id"],
        "when": {"type": "time", "at": "03:00"}, "then": {"control": "power", "value": "off"}},
    ).json()["id"]
    upd = client.patch(f"/api/rules/{rid}", headers=dev_headers, json={"enabled": False, "name": "renamed"}).json()
    assert upd["enabled"] is False and upd["name"] == "renamed"
    assert client.delete(f"/api/rules/{rid}", headers=dev_headers).status_code == 204
    ids = [r["id"] for r in client.get("/api/rules", headers=dev_headers).json()]
    assert rid not in ids


def test_time_rules_fire_in_local_timezone(client, dev_headers, devices):
    # A wall-clock time like "19:00" means 7pm in the configured local zone
    # (Asia/Ho_Chi_Minh, UTC+7), not 19:00 UTC. Before the fix a rule typed in local
    # time was evaluated against the server's UTC clock and never matched.
    from datetime import datetime, timezone

    from app.core.clock import Clock, FrozenClock, set_clock
    from app.database import SessionLocal
    from app.domain.models import Rule
    from app.services.rule_engine import RuleEngine

    plug = device_of(devices, "plug")
    rid = client.post("/api/rules", headers=dev_headers, json={
        "name": "tv off at 7pm", "device_id": plug["id"], "auto_apply": True,
        "when": {"type": "time", "at": "19:00"},
        "then": {"control": "power", "value": "off"}},
    ).json()["id"]

    db = SessionLocal()
    try:
        engine = RuleEngine(db)
        rule = db.get(Rule, rid)
        # 12:00 UTC == 19:00 in Asia/Ho_Chi_Minh -> the condition holds.
        set_clock(FrozenClock(datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)))
        assert engine.evaluate(rule) is True
        # 19:00 UTC == 02:00 local -> it must NOT hold.
        set_clock(FrozenClock(datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc)))
        assert engine.evaluate(rule) is False
    finally:
        set_clock(Clock())  # restore real clock for the session-scoped client
        db.close()
        client.delete(f"/api/rules/{rid}", headers=dev_headers)


def test_rule_is_idempotent_when_target_already_satisfied(client, dev_headers, devices):
    # Regression: a "set AC target to 26" rule must NOT keep firing (and notifying)
    # once the target is already 26. Applying a RANGE command stores the value as a
    # normalized float (26.0); the idempotency check must still treat that as equal to
    # the rule's literal 26, instead of failing a naive "26.0" == "26" string compare.
    from app.database import SessionLocal
    from app.domain.models import Device, Rule
    from app.services.rule_engine import RuleEngine

    ac = device_of(devices, "ac")
    client.post(f"/api/devices/{ac['id']}/connectivity?online=true", headers=dev_headers)
    db = SessionLocal()
    try:  # clear the compressor rate-limit timer so the setup command applies cleanly
        d = db.get(Device, ac["id"])
        s = dict(d.state or {})
        s.pop("last_ac_cmd_ts", None)
        d.state = s
        db.commit()
    finally:
        db.close()

    # Drive the target to 26 -> stored state holds the normalized float 26.0.
    res = client.post(f"/api/devices/{ac['id']}/command", headers=dev_headers,
                      json={"control": "target", "value": 26}).json()
    assert res["outcome"] == "success"

    rid = client.post("/api/rules", headers=dev_headers, json={
        "name": "hold ac at 26", "device_id": ac["id"], "auto_apply": True,
        "when": {"type": "time", "between": ["00:00", "23:59"]},
        "then": {"control": "target", "value": 26}},
    ).json()["id"]

    db = SessionLocal()
    try:
        engine = RuleEngine(db)
        # Device already at 26.0 -> idempotent -> no execution and no notification.
        assert engine.execute(db.get(Rule, rid)) is None
    finally:
        db.close()
        client.delete(f"/api/rules/{rid}", headers=dev_headers)


def test_execution_logging_undo_and_history_preserved(client, dev_headers, devices):
    # REQ-4.3.5 logging, REQ-4.3.6 undo, Business Rule: deleting a rule keeps history.
    from app.database import SessionLocal
    from app.domain.enums import CommandOutcome, Initiator
    from app.domain.models import Rule, RuleExecution
    from app.services.rule_engine import RuleEngine

    me = client.get("/api/auth/me", headers=dev_headers).json()
    home_id = me["home_id"]
    plug = device_of(devices, "plug")  # non-safety TV plug
    client.post(f"/api/devices/{plug['id']}/command", headers=dev_headers,
                json={"control": "power", "value": "on"})
    rid = client.post("/api/rules", headers=dev_headers, json={
        "name": "auto off test", "device_id": plug["id"], "auto_apply": True,
        "when": {"type": "time", "between": ["00:00", "23:59"]},
        "then": {"control": "power", "value": "off"}},
    ).json()["id"]

    db = SessionLocal()
    try:
        engine = RuleEngine(db)
        execution = engine.execute(db.get(Rule, rid), Initiator.SCHEDULER)
        assert execution is not None
        assert execution.outcome == CommandOutcome.SUCCESS
        assert execution.undo_deadline is not None  # reversible -> undoable
        ex_id = execution.id
        restored = engine.undo(ex_id, home_id)
        assert restored.undone is True
    finally:
        db.close()

    # REQ-4.3.5: execution retrievable through the API.
    execs = client.get(f"/api/rules/{rid}/executions", headers=dev_headers).json()
    assert any(e["outcome"] == "success" for e in execs)

    # Deleting the rule must NOT delete its execution history (Business Rule).
    client.delete(f"/api/rules/{rid}", headers=dev_headers)
    db = SessionLocal()
    try:
        remaining = db.query(RuleExecution).filter(RuleExecution.rule_id == rid).count()
        assert remaining >= 1
    finally:
        db.close()
