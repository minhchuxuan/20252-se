"""Known-issue tests — these are EXPECTED TO FAIL.

They document open defects in rule authoring/validation where the system either
returns a hard error when a softer outcome (a warning, a sensible default, a clean
rejection) is appropriate, or silently accepts input it should question. They assert
the *desired* behaviour, so they fail against the current implementation on purpose.

Per request: these are written to fail and are NOT fixed here. They are isolated in
this file so the 67-test acceptance suite stays green; run just these with
``pytest tests/test_known_issues.py``.
"""
from tests.conftest import device_of

_FAN_WHEN = {"type": "time", "between": ["12:00", "14:00"]}
_POWER_ON = {"control": "power", "value": "on"}


def test_blank_rule_name_should_not_hard_error(client, dev_headers, devices):
    # ISSUE: submitting a rule with no name returns 422 (Pydantic min_length=1)
    # instead of being accepted with a sensible default name (e.g. the WHEN-THEN
    # summary) or surfaced as a soft, non-blocking warning. A missing name is a
    # convenience gap, not an invalid rule.
    fan = device_of(devices, "fan")
    body = {"name": "", "device_id": fan["id"], "when": _FAN_WHEN, "then": _POWER_ON}
    res = client.post("/api/rules", headers=dev_headers, json=body)
    rid = res.json().get("id") if res.status_code == 201 else None
    try:
        assert res.status_code == 201, f"blank name hard-errored: {res.status_code} {res.text}"
    finally:
        if rid:
            client.delete(f"/api/rules/{rid}", headers=dev_headers)


def test_validate_blank_name_should_warn_not_error(client, dev_headers, devices):
    # ISSUE: /rules/validate does not even use the name (it only checks the device,
    # condition, action, conflicts and estimate), yet a blank name makes it return
    # 422 before any validation runs. The pre-save check should succeed and, at most,
    # carry a warning that a name is required before the rule can be saved.
    fan = device_of(devices, "fan")
    body = {"name": "", "device_id": fan["id"], "when": _FAN_WHEN, "then": _POWER_ON}
    res = client.post("/api/rules/validate", headers=dev_headers, json=body)
    assert res.status_code == 200, f"validate hard-errored on a blank name: {res.status_code}"


def test_whitespace_only_name_should_be_trimmed_or_defaulted(client, dev_headers, devices):
    # ISSUE: a whitespace-only name ("   ") slips past min_length=1 and is stored
    # verbatim, so the rule lists with a blank label. The name should be trimmed and,
    # if empty after trimming, defaulted (not stored blank).
    fan = device_of(devices, "fan")
    body = {"name": "   ", "device_id": fan["id"], "when": _FAN_WHEN, "then": _POWER_ON}
    res = client.post("/api/rules", headers=dev_headers, json=body)
    rid = res.json().get("id") if res.status_code == 201 else None
    try:
        assert rid is not None, f"creation failed: {res.status_code} {res.text}"
        assert res.json()["name"].strip() != "", "rule stored a blank (whitespace-only) name"
    finally:
        if rid:
            client.delete(f"/api/rules/{rid}", headers=dev_headers)


def test_malformed_time_window_should_be_rejected_cleanly(client, dev_headers, devices):
    # ISSUE: a malformed time such as "25:00" passes validation (only presence of
    # at/between is checked, never the HH:MM format), so the rule is created and later
    # raises ValueError when the scheduler evaluates it. The validator should reject a
    # malformed time cleanly (422) at authoring time.
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
    # ISSUE: creating a second rule identical to an existing one (same device, same
    # WHEN, same THEN) is allowed silently — conflict detection treats an identical
    # command as "not a conflict" — producing redundant rules and duplicate
    # notifications. The validator should flag the duplicate.
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


def test_negative_tariff_price_should_be_rejected(client, admin_headers):
    # ISSUE: TariffCreate.config is a free-form dict with no validation, so a flat
    # tariff with a negative price is accepted and would produce negative bills/savings.
    # A non-positive price should be rejected (422). (Tariffs are Administrator-managed,
    # so this uses admin_headers; the original active tariff is restored afterwards so
    # the shared suite is unaffected.)
    before = client.get("/api/tariffs", headers=admin_headers).json()
    active_before = next((t["id"] for t in before if t["active"]), None)
    body = {"name": "bad tariff", "type": "flat", "config": {"price": -5000}}
    res = client.post("/api/tariffs", headers=admin_headers, json=body)
    try:
        assert res.status_code == 422, (
            f"negative tariff price was accepted ({res.status_code}) instead of rejected"
        )
    finally:
        # Creating a tariff activates it; restore the original so other suites see the
        # real (positive) building tariff.
        if res.status_code == 201 and active_before is not None:
            client.put(f"/api/tariffs/{active_before}/activate", headers=admin_headers)
