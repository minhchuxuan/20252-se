# Test Plan & Report — AI-Driven Smart Home Energy Optimizer

> IT3180E Introduction to Software Engineering — Verification & Validation (Lecture 15: Software Testing).
> This plan documents the testing strategy, levels, black-box techniques, environment, a requirements→test
> traceability catalogue, and the current results for the **54 automated tests** in
> [`backend/tests/`](../backend/tests). Every test name and assertion cited below was read from the actual
> source files.

---

## 1. Objectives & Scope

### 1.1 Objectives

The testing effort verifies that the implemented system satisfies the requirements in the SRS
(`srs_final.md` §4–§5) and the acceptance-test focus areas in `refine_note.md` §10. Concretely, the test
suite aims to:

- **Validate functional behaviour** for each requirement family REQ-4.1 (monitoring) through REQ-4.5
  (bill-saving estimation), so that requirements are traceable to executable checks.
- **Verify safety and security** non-functional requirements: AC compressor rate limiting (NFR-SAF-1),
  safety-critical power-off protection (NFR-SAF-2), validation warnings (NFR-SAF-3), authentication and
  RBAC (NFR-SEC-2), and never storing plaintext secrets (NFR-SEC-3).
- **Pin down business rules** that are easy to regress, e.g. *deleting a rule must not delete its execution
  history*, *auto-action is off by default*, and *only Owner manages devices/family*.
- **Guard the design contract** that makes the architecture defensible: that the **capability schema**
  drives both rendering and validation, and that the **mock simulator** makes every functional requirement
  testable without hardware.

### 1.2 In Scope

- Backend domain logic, services, and HTTP API (FastAPI), exercised through `pytest` with the in-process
  `TestClient`.
- The deterministic, rule-based optimization/recommendation logic and tariff math.
- The mock device simulator and adapter Strategy implementations as the system-under-test for telemetry.

### 1.3 Out of Scope (current automated suite)

- **Frontend UI** (React/Recharts) is verified manually against acceptance criteria; it is not covered by
  the automated suite (the capability *contract* it depends on **is** covered server-side).
- **Live WebSocket push** (`api/ws.py` `ConnectionManager`) and **TLS/WSS** (NFR-SEC-1) are deployment
  concerns; the suite tests the event/notification *production* path (services) rather than socket transport.
- **Load/concurrency** targets (NFR-PER-3, 100 simulated homes) are design-level, validated by the async
  architecture rather than an automated load test.

---

## 2. Test Levels

The suite is organised along the classic V-model levels. The split is **physical**: pure-logic unit tests
have no HTTP/DB, while every other file drives the running application through `TestClient`, giving
integration- and system-level coverage in one harness.

| Level | What it checks | Where it lives |
| --- | --- | --- |
| **Unit** | Pure domain functions in isolation (no HTTP, no DB): capability validator, tariff pricing math, billing-cycle/time utilities, simulator energy model, password hashing. | [`test_unit_domain.py`](../backend/tests/test_unit_domain.py) — 10 test functions; `test_ac_target_boundaries` is parametrized into 6 cases. |
| **Integration** | Multiple layers cooperating across a real boundary — API router → service → repository → SQLAlchemy/SQLite, plus EventBus and adapter wiring. Several tests also call services directly (`RuleEngine`, `DeviceService`) against `SessionLocal` to assert side-effects the API alone does not expose. | [`test_auth_rbac.py`](../backend/tests/test_auth_rbac.py), [`test_devices_capability.py`](../backend/tests/test_devices_capability.py), [`test_rules.py`](../backend/tests/test_rules.py), [`test_safety.py`](../backend/tests/test_safety.py) |
| **System** | End-to-end behaviour of a fully seeded application through public endpoints — dashboards, reports, recommendations, and savings produced from 21 days of real telemetry. | [`test_monitoring.py`](../backend/tests/test_monitoring.py), [`test_recommendations.py`](../backend/tests/test_recommendations.py), [`test_savings.py`](../backend/tests/test_savings.py) |
| **Acceptance** | The `refine_note.md` §10 focus items, demonstrated through the system/integration tests above against the demo seed and the three demo accounts. | Mapped explicitly in §5 below. |

> **Note on the integration/system overlap.** Because the same `TestClient` fixture (a fully booted,
> seeded application) backs both the integration and system files, the distinction is one of *intent*:
> integration files target a specific cross-layer mechanism (e.g. capability validation, RBAC, conflict
> detection), while system files assert aggregate, user-visible outputs (dashboard metrics, ranked
> recommendations, cycle savings). The acceptance level is not a separate file — it is the §10 checklist
> realised by the union of these tests.

---

## 3. Black-Box Test-Design Techniques

The suite deliberately applies the techniques from the SE testing lecture rather than testing ad hoc.

### 3.1 Equivalence Partitioning (EP)

The AC `target` control accepts an integer in **[16, 30] °C**. Inputs are partitioned into:

- **Valid class** — any value inside the range (representative: 23).
- **Invalid-low class** — values below 16.
- **Invalid-high class** — values above 30.

`test_ac_target_boundaries` in [`test_unit_domain.py`](../backend/tests/test_unit_domain.py) covers the
valid class with 23 and the invalid classes with 15, 31 and −5. Partitioning is also applied to enumerated
and toggle controls in `test_validate_enum_and_toggle` (valid `mode="sleep"` / `power="on"` vs invalid
`mode="turbo"` / `power="maybe"`) and to *unsupported controls* in `test_validate_rejects_unknown_control`
(`brightness` on a plug → rejected with "no control").

### 3.2 Boundary-Value Analysis (BVA)

For the same AC `target` range, the boundaries and their immediate neighbours are tested explicitly:

| Input | Class | Expected | Asserted in |
| --- | --- | --- | --- |
| **16** | lower boundary (valid) | accept | `test_ac_target_boundaries` |
| **30** | upper boundary (valid) | accept | `test_ac_target_boundaries` |
| **23** | nominal interior | accept | `test_ac_target_boundaries` |
| **15** | just below lower boundary | reject | `test_ac_target_boundaries` |
| **31** | just above upper boundary | reject | `test_ac_target_boundaries` |
| **−5** | far invalid (negative) | reject | `test_ac_target_boundaries` |

This is the canonical BVA "min, min−1, max, max+1, nominal" set, plus an out-of-domain negative, run as a
single parametrized test (6 cases) directly against `validate_command(DeviceType.AC, "target", value)`.

### 3.3 Decision-Table / Rule-Based Testing

Behaviour that depends on a *combination* of conditions is covered with decision-table thinking:

- **Command outcome** depends on (device online?) × (value in range?) × (safety-critical?) × (rate-limited?),
  producing the outcomes `success` / `rejected` / `timeout` / `skipped`:
  - online + in-range → `success` and online + out-of-range → `rejected`
    (`test_command_validation_rejects_out_of_range`).
  - offline → `timeout` (`test_offline_device_command_times_out`).
  - second compressor command within 3 min → `rejected` "rate limit"
    (`test_ac_compressor_rate_limit`).
  - auto power-off of safety-critical device → `skipped` "safety-critical"
    (`test_safety_critical_device_not_auto_powered_off`).
- **Validation warnings** form a decision table over (temperature change?) / (safety-critical tag?) /
  (unattended power-off?) in `test_safety_warnings_on_validation`.

### 3.4 Use-Case / Scenario-Based Testing

The §7 use cases are tested as end-to-end scenarios:

- **Add Mock Device** → `test_add_and_delete_mock_device`, `test_mock_profiles_available`.
- **Control Device Feature** (fetch capabilities → render-eligible controls → validate → outcome) →
  `test_capability_endpoint_drives_controls` + `test_command_validation_rejects_out_of_range`.
- **Accept Recommendation** (readable WHEN-THEN → estimate → accept → becomes rule) →
  `test_accept_recommendation_becomes_rule`, `test_dismiss_suppresses_recommendation`.

---

## 4. Test Environment & How to Run

### 4.1 Environment

| Aspect | Configuration |
| --- | --- |
| Runner | `pytest` |
| Application | FastAPI app imported as `app.main:app`, driven in-process by Starlette's `TestClient`. |
| Database | A throwaway SQLite file `/tmp/sheo_test_<pid>.db`, recreated per run and deleted at session teardown. |
| Seed | `SHEO_SEED_ON_STARTUP=1` — the full demo seed loads (1 home, 3 users, tiered EVN tariff, 6 devices including an occupancy sensor and a safety-critical fridge, **21 days** of telemetry, one accepted auto-rule, measured savings, generated recommendations) so acceptance tests have realistic data. |
| Background workers | `SHEO_ENABLE_BACKGROUND=0` — the live simulator **and** scheduler are **disabled** for determinism (no clock-driven telemetry or rule firing during assertions). |
| Auth | A session-scoped `TestClient` plus `owner_headers` / `family_headers` / `dev_headers` fixtures that log in the demo accounts (`*@demo.com`, password `demo1234`) and carry Bearer tokens. |

These environment variables are set in [`conftest.py`](../backend/tests/conftest.py) **before** the app is
imported, because settings are cached at import time. A `devices` fixture and a `device_of(devices, dtype)`
helper give tests easy access to the seeded devices by type.

### 4.2 Commands

```bash
cd project/backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest                 # runs all 54 tests
pytest -v              # show each test id
pytest tests/test_unit_domain.py   # run a single level (pure unit)
```

No network, no real hardware, and no running Uvicorn server are required — the suite is fully
self-contained and deterministic.

---

## 5. Test-Case Catalogue (Acceptance §10 → Tests)

The table maps each `refine_note.md` §10 acceptance focus item to the requirement(s) it realises and the
**exact** test function(s) that exercise it.

| # | §10 Acceptance item | Requirement(s) | Covering test function(s) (file) |
| --- | --- | --- | --- |
| 1 | **Telemetry refresh** (instantaneous W + cumulative kWh) | REQ-4.1.1 / 4.1.2 | `test_dashboard_reports_home_metrics` (test_monitoring.py) — asserts `home_total_w`, `kwh_today`, `kwh_cycle`, `estimated_bill_vnd`, `savings_cycle_vnd`, `devices` present and `kwh_cycle ≥ kwh_today ≥ 0`. Series buckets: `test_consumption_series_buckets`. |
| 2 | **Device offline detection** | REQ-4.1.4 | `test_offline_device_command_times_out` (test_devices_capability.py) — forces connectivity off, then asserts the dashboard marks the device `online: false`. |
| 3 | **Device capability loading** (fetch schema before rendering) | REQ-4.2.1 | `test_capability_endpoint_drives_controls` (test_devices_capability.py) — `GET /devices/{id}/capabilities` returns exactly `{power, target, mode}` and the `target` control is a `range` with `min=16, max=30`. Bulb case: `test_add_and_delete_mock_device`. |
| 4 | **Command validation** (range check, outcome) | REQ-4.2.3 / 4.2.4 | `test_command_validation_rejects_out_of_range` (test_devices_capability.py) — value 25 → `success`, value 99 → `rejected`. Pure-logic BVA/EP: `test_ac_target_boundaries`, `test_validate_enum_and_toggle`, `test_validate_rejects_unknown_control`, `test_sensor_is_readonly` (test_unit_domain.py). |
| 5 | **Mock-device operation** | REQ-4.2.5 | `test_mock_profiles_available` (plug/bulb/fan/ac/sensor profiles exist) and `test_add_and_delete_mock_device` (create → has `brightness` control → delete 204), both test_devices_capability.py. Energy model: `test_simulator_ac_savings_differential` (test_unit_domain.py). |
| 6 | **Rule creation & conflict detection** | REQ-4.3.2 / 4.3.3 / 4.3.4 | `test_conflict_detection` (overlapping-time opposing commands → `conflicts ≥ 1`); `test_action_must_match_capability` (plug+`brightness` → invalid, POST 422); `test_enable_disable_edit_delete`; `test_auto_action_off_by_default` (all test_rules.py). |
| 7 | **Recommendation approval flow** | REQ-4.4.1–4.4.5 | `test_accept_recommendation_becomes_rule` (accept → rule appears, rec disappears); `test_recommendations_are_readable_and_explainable` (WHEN-THEN + rationale + data window + VND > 0); `test_recommendations_ranked_and_capped` (sorted desc, ≤ 5); `test_new_device_without_history_yields_no_recommendation` (REQ-4.4.1 ≥ 7 days); `test_dismiss_suppresses_recommendation` (all test_recommendations.py). |
| 8 | **VND saving estimate display (before save)** | REQ-4.5.1 / 4.5.2 / 4.5.3 | `test_estimate_before_save_uses_srs_formula` (test_savings.py) — `baseline_kwh_month > 0`, `expected = 0` for off-window, `saved_vnd = saved_kwh × tariff`. `test_raising_ac_target_saves_energy` checks the AC case. |
| 9 | **Current billing-cycle saving display** | REQ-4.5.4 | `test_savings_summary_reports_cycle` (currency VND, `saved_vnd_cycle ≥ 0`, `cycle_start < cycle_end`) and `test_savings_records_present` (a `measured` record exists), both test_savings.py. Cycle figure also surfaced by `test_dashboard_reports_home_metrics` (`savings_cycle_vnd`). |
| 10 | **Notification delivery** | SRS 3.3 / REQ-4.1.4 | **Indirect:** the notification *production* path is driven by the offline trigger in `test_offline_device_command_times_out` (DEVICE_OFFLINE) and the rule-fired path in `test_execution_logging_undo_and_history_preserved` (RULE_FIRED). `NotificationService.create` re-publishes to the WebSocket broadcaster. See §6.3 (known limitation: no dedicated `GET /notifications` assertion). |
| 11 | **Auto-action opt-in & Undo** | REQ-4.3.5 / 4.3.6 | `test_auto_action_off_by_default` (REQ-4.3.6 default `auto_apply=False`, summary has WHEN/THEN) and `test_execution_logging_undo_and_history_preserved` (executes an auto rule, asserts `undo_deadline` set, `undo()` → `undone=True`, execution retrievable via API, history survives rule deletion), both test_rules.py. |
| 12 | **Safety-critical device protection** | NFR-SAF-1 / 2 / 3 | `test_safety_critical_device_not_auto_powered_off` (scheduler power-off → `SKIPPED` "safety-critical"); `test_ac_compressor_rate_limit` (2nd command in 3 min → `rejected` "rate limit"); `test_safety_warnings_on_validation` (temperature + safety-critical warnings), all test_safety.py. |

**Supporting tests not tied to a single §10 row** (security & business-rule guards):

- Authentication & RBAC — `test_login_returns_token_and_user`, `test_login_rejects_bad_password`,
  `test_unauthenticated_request_is_rejected`, `test_me_returns_current_user`,
  `test_family_cannot_add_device`, `test_family_cannot_create_tariff`,
  `test_owner_can_create_family_member` (test_auth_rbac.py) — covers NFR-SEC-2, NFR-SEC-4 and the
  Owner-only management business rule, including per-device permission scoping for a new family member.
- Secrets — `test_password_hash_roundtrip_never_plaintext` (NFR-SEC-3).
- Tariff math — `test_flat_tariff_pricing`, `test_tiered_tariff_is_progressive`,
  `test_billing_cycle_contains_now`, `test_hour_set_wraps_midnight` (REQ-4.5 pricing & time windows).
- Reporting — `test_top_consumers_ranked` (REQ-4.1.5, ranked desc with `cost_vnd`/`share_pct`),
  `test_csv_export` (data export, `text/csv` with the expected header).

---

## 6. Results Summary, Coverage Notes & Known Limitations

### 6.1 Results

```
$ pytest
============================ 54 passed ============================
```

All **54 tests pass** (collected as 54: 46 declared `def test_*` functions, with two
parametrized tests expanding — `test_ac_target_boundaries` → 6 cases (+5) and
`test_power_on_off_control` → 4 cases (+3)). Distribution by file:

| File | Functions | Notes |
| --- | --- | --- |
| `test_unit_domain.py` | 10 (15 cases) | Pure unit; BVA/EP, tariff & time math, simulator, hashing. |
| `test_auth_rbac.py` | 7 | Auth + RBAC + family permissions. |
| `test_devices_capability.py` | 6 (9 cases) | Capability schema, on/off control, commands, offline, mock CRUD. |
| `test_rules.py` | 5 | Rules, conflict, edit/delete, exec log + undo + history. |
| `test_recommendations.py` | 5 | Recommendation generation, ranking, accept/dismiss. |
| `test_monitoring.py` | 5 | Dashboard, top consumers, series, CSV export, cross-home isolation. |
| `test_savings.py` | 5 | Estimate (SRS formula), AC case, cycle summary, records, drift check. |
| `test_safety.py` | 3 | Rate limit, safety-critical protection, warnings. |
| **Total** | **46 → 54 collected** | |

### 6.2 Coverage Notes

- **Requirements coverage is broad and traceable:** every REQ family (4.1–4.5) and every safety/security
  NFR with observable behaviour has at least one dedicated test, and §5 maps all twelve §10 acceptance
  items to concrete functions.
- **Both test styles are present:** pure-logic unit tests pin the algorithms (validation, pricing, simulator
  energy differential), while seeded `TestClient` tests prove the wired system behaves correctly through its
  public API.
- **Design contracts are protected by tests**, not just documented: the capability schema (rendering +
  validation), the Strategy adapters via the simulator, and the *no-cascade* execution-history business rule
  are each asserted.
- **Negative and boundary paths are first-class:** rejected/timeout/skipped command outcomes, out-of-range
  and unsupported controls, bad password, unauthenticated access, and forbidden cross-role actions are all
  explicitly exercised.

### 6.3 Known Limitations

1. **Notification delivery is covered indirectly.** The suite triggers the event paths that *produce*
   notifications (device-offline, rule-fired) but does not assert against `GET /notifications` nor open a
   real WebSocket. *Mitigation / future work:* add a test that, after the offline trigger, asserts a
   `DEVICE_OFFLINE` notification is returned by `GET /notifications`, and a `TestClient.websocket_connect`
   smoke test for the broadcaster.
2. **Frontend is not in the automated suite.** React control rendering is validated manually; the
   server-side capability contract it consumes *is* tested.
3. **Background scheduler/simulator are disabled during tests** for determinism, so time-driven auto-firing
   is exercised by invoking `RuleEngine.execute(...)` directly rather than by waiting on the live scheduler.
4. **Non-functional performance/scale (NFR-PER-3, TLS/WSS NFR-SEC-1)** are not load-tested; they rest on the
   async architecture and deployment configuration and would be validated with a separate load harness.
5. **No automated line-coverage gate** is configured yet. *Future work:* add `pytest --cov` with a coverage
   threshold to CI to keep the requirement→test mapping honest as the code grows.
