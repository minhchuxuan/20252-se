"""Known-issue tests — these are EXPECTED TO FAIL (3 cases).

They document open defects in rule authoring/validation where the system either
returns a hard error when a softer outcome (a warning, a sensible default, a clean
rejection) is appropriate, or silently accepts input it should question. They assert
the *desired* behaviour, so they fail against the current implementation on purpose.

Per request: these are written to fail and are NOT fixed here. With them, the suite
is 70 tests: 67 pass and these 3 fail. They mirror KI-1..KI-3 in the report's
open-defect table. Run just these with ``pytest tests/test_known_issues.py``.
"""
from tests.conftest import device_of

_FAN_WHEN = {"type": "time", "between": ["12:00", "14:00"]}
_POWER_ON = {"control": "power", "value": "on"}


def test_blank_rule_name_should_not_hard_error(client, dev_headers, devices):
    # KI-1. ISSUE: submitting a rule with no name returns 422 (Pydantic min_length=1)
    # instead of being accepted with a sensible default name (e.g. the WHEN-THEN
    # summary) or surfaced as a soft, non-blocking warning. A missing name is a
    # convenience gap, not an invalid rule. (Equivalence partitioning: empty-name class.)
    fan = device_of(devices, "fan")
    body = {"name": "", "device_id": fan["id"], "when": _FAN_WHEN, "then": _POWER_ON}
    res = client.post("/api/rules", headers=dev_headers, json=body)
    rid = res.json().get("id") if res.status_code == 201 else None
    try:
        assert res.status_code == 201, f"blank name hard-errored: {res.status_code} {res.text}"
    finally:
        if rid:
            client.delete(f"/api/rules/{rid}", headers=dev_headers)


def test_malformed_time_window_should_be_rejected_cleanly(client, dev_headers, devices):
    # KI-2. ISSUE: a malformed time such as "25:00" passes validation (only presence of
    # at/between is checked, never the HH:MM format), so the rule is created and later
    # raises ValueError when the scheduler evaluates it. The validator should reject a
    # malformed time cleanly (422) at authoring time. (BVA: hour-of-day boundary 24:00.)
    fan = device_of(devices, "fan")
    body = {"name": "bad time", "device_id": fan["id"],
            "when": {"type": "time", "between": ["25:00", "26:00"]}, "then": _POWER_ON}
    res = client.post("/api/rules", headers=dev_headers, json=body)
    rid = res.json().get("id") if res.status_code == 201 else None
    try:
        assert res.status_code == 422, (
            f"malformed time '25:00' was accepted ({res.status_code}) instead of rejected"
        )
    finally:
        if rid:
            client.delete(f"/api/rules/{rid}", headers=dev_headers)


def test_duplicate_identical_rule_should_be_flagged(client, dev_headers, devices):
    # KI-3. ISSUE: creating a second rule identical to an existing one (same device, same
    # WHEN, same THEN) is allowed silently — conflict detection treats an identical
    # command as "not a conflict" — producing redundant rules and duplicate
    # notifications. The validator should flag the duplicate. (Decision table.)
    fan = device_of(devices, "fan")
    base = {"name": "dup one", "device_id": fan["id"], "when": _FAN_WHEN, "then": _POWER_ON}
    first = client.post("/api/rules", headers=dev_headers, json=base)
    rid = first.json().get("id") if first.status_code == 201 else None
    try:
        assert rid is not None, f"setup creation failed: {first.status_code} {first.text}"
        dup = {**base, "name": "dup two"}
        val = client.post("/api/rules/validate", headers=dev_headers, json=dup).json()
        flagged = bool(val.get("conflicts")) or any(
            "duplicate" in w.lower() for w in val.get("warnings", [])
        )
        assert flagged, "an identical duplicate rule was not flagged by validation"
    finally:
        if rid:
            client.delete(f"/api/rules/{rid}", headers=dev_headers)
