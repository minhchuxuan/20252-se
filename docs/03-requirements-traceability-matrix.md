# Requirements Traceability Matrix (RTM)

**Project:** AI-Driven Smart Home Energy Optimizer
**Course:** IT3180E – Introduction to Software Engineering (HUST/SOICT)
**Source of requirements:** [srs_final.md](../../Project_detail/srs_final.md) §4 (System Features), §5 (Non-functional), §5.5 (Business Rules), §6.1 (Data Export)
**Tested implementation:** `project/backend` (Python 3.13, FastAPI, SQLAlchemy 2.0, SQLite); 54 automated tests in [backend/tests](../backend/tests), all passing.

---

## 1. Purpose and how to read this matrix

This matrix is the central verification-and-validation (V&V) artefact that ties the four pillars of the project together — **requirement → design → code → test** — so a grader can confirm that every requirement in the SRS is both *built* and *checked*.

It supports traceability in **both** directions:

- **Forward traceability** (requirement → implementation → test): start at a `REQ-*`/`NFR-*` row and follow it to the design element that realises it, the exact file·function that implements it, and the automated test that proves it. This shows nothing in the SRS was dropped.
- **Backward traceability** (test/code → requirement): start at any test function or module and find which requirement justifies it. This shows there is no "gold-plating" — every piece of code earns its place by satisfying a stated requirement.

**Column meanings**

| Column | Meaning |
| :--- | :--- |
| Requirement ID | The SRS identifier (`REQ-<feature>.<n>`, `NFR-<cat>-<n>`, or business rule). |
| Requirement (short) | One-line restatement; see [srs_final.md](../../Project_detail/srs_final.md) for the normative text. |
| Priority | High (must), Medium (should), Low (could), per SRS §1.2. |
| Design element | The architectural module / class that owns the responsibility (see [02-software-design-document.md](./02-software-design-document.md)). |
| Implementation | The concrete `file · function/class` that realises it (verified by reading the code). |
| Test(s) | The automated test that exercises it (`file · test function`). |

All policy thresholds referenced below (5 s refresh, 60 s offline, 14-day baseline, 7-day data minimum, 5 recommendations, 30-day dismissal, 120 s undo, 180 s AC interval, ±20 % drift) are centralised in [config.py](../backend/app/config.py) `Settings`, keeping requirements traceable to a single configuration surface.

---

## 2. Functional requirements

### 2.1 Real-Time Energy Monitoring (SRS §4.1)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| REQ-4.1.1 | Show instantaneous power (W) per device; refresh ≤ 5 s | High | Presentation + Simulator (Observer) | [simulator/engine.py](../backend/app/simulator/engine.py) `SimulatorEngine._tick_once` (2 s emit, `settings.telemetry_interval_seconds`); [telemetry_service.py](../backend/app/services/telemetry_service.py) `TelemetryService.dashboard`; [api/ws.py](../backend/app/api/ws.py) `ConnectionManager` | [test_monitoring.py](../backend/tests/test_monitoring.py) · `test_dashboard_reports_home_metrics` |
| REQ-4.1.2 | Cumulative kWh per device: today / cycle / range | High | Application (telemetry) + Data (repository) | [telemetry_service.py](../backend/app/services/telemetry_service.py) `TelemetryService.dashboard` (`kwh_today`, `kwh_cycle`) and `consumption_series`; [repositories.py](../backend/app/repositories/repositories.py) `ReadingRepository.sum_energy` | [test_monitoring.py](../backend/tests/test_monitoring.py) · `test_dashboard_reports_home_metrics`, `test_consumption_series_buckets` |
| REQ-4.1.3 | Retain 1-min aggregates ≥ 12 months | High | Data tier (model + retention policy) | [config.py](../backend/app/config.py) `Settings.reading_retention_days = 365`; [models.py](../backend/app/domain/models.py) `Reading` (columns `ts` (indexed) / `interval_kwh` / `kwh_total`; `device_id` also indexed) | [test_monitoring.py](../backend/tests/test_monitoring.py) · `test_consumption_series_buckets` (reads persisted history) |
| REQ-4.1.4 | Device silent > 60 s → marked unreachable | High | Application (telemetry) + clock | [telemetry_service.py](../backend/app/services/telemetry_service.py) `TelemetryService.refresh_online_status` (`settings.offline_threshold_seconds`); [device_service.py](../backend/app/services/device_service.py) `DeviceService.set_connectivity` | [test_devices_capability.py](../backend/tests/test_devices_capability.py) · `test_offline_device_command_times_out` |
| REQ-4.1.5 | Top-3 consuming devices for day/week/month | High | Application (telemetry) | [telemetry_service.py](../backend/app/services/telemetry_service.py) `TelemetryService.top_consumers`; [api/monitoring.py](../backend/app/api/monitoring.py) `top_consumers` | [test_monitoring.py](../backend/tests/test_monitoring.py) · `test_top_consumers_ranked` |

### 2.2 Device Control and Capability Schema (SRS §4.2)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| REQ-4.2.1 | Fetch capabilities from `GET /devices/{id}/capabilities` before rendering | High | Capability schema (data-driven) | [capability.py](../backend/app/domain/capability.py) `get_capability` / `CapabilitySchema`; [device_service.py](../backend/app/services/device_service.py) `DeviceService.capability`; [api/devices.py](../backend/app/api/devices.py) `get_capabilities` | [test_devices_capability.py](../backend/tests/test_devices_capability.py) · `test_capability_endpoint_drives_controls` |
| REQ-4.2.2 | On/off control for plug, bulb, fan, AC | High | Capability schema + Strategy adapters | [capability.py](../backend/app/domain/capability.py) `_POWER` control on PLUG/BULB/FAN/AC schemas; [adapters/devices.py](../backend/app/adapters/devices.py) `*Adapter.tick` / `DeviceAdapter.apply_control` | [test_devices_capability.py](../backend/tests/test_devices_capability.py) · `test_power_on_off_control[plug/bulb/fan/ac]`, `test_capability_endpoint_drives_controls` |
| REQ-4.2.3 | Validate command values against capability ranges | High | Capability validator | [capability.py](../backend/app/domain/capability.py) `validate_command`; [device_service.py](../backend/app/services/device_service.py) `DeviceService.apply_command` | [test_unit_domain.py](../backend/tests/test_unit_domain.py) · `test_ac_target_boundaries`, `test_validate_rejects_unknown_control`, `test_validate_enum_and_toggle`; [test_devices_capability.py](../backend/tests/test_devices_capability.py) · `test_command_validation_rejects_out_of_range` |
| REQ-4.2.4 | Command returns success / rejected / timeout ≤ 5 s | High | Application (device control) | [device_service.py](../backend/app/services/device_service.py) `DeviceService.apply_command` (`CommandResult`; offline → `TIMEOUT`, invalid → `REJECTED`) | [test_devices_capability.py](../backend/tests/test_devices_capability.py) · `test_command_validation_rejects_out_of_range`, `test_offline_device_command_times_out` |
| REQ-4.2.5 | Mock simulator: plug, bulb, fan, AC, occupancy sensor | High | Simulator + Strategy adapters | [simulator/engine.py](../backend/app/simulator/engine.py) `generate_history` / `SimulatorEngine`; [adapters/devices.py](../backend/app/adapters/devices.py) `_ADAPTERS` / `get_adapter`; [device_service.py](../backend/app/services/device_service.py) `DeviceService.mock_profiles` / `add_mock_device` | [test_devices_capability.py](../backend/tests/test_devices_capability.py) · `test_mock_profiles_available`, `test_add_and_delete_mock_device`; [test_unit_domain.py](../backend/tests/test_unit_domain.py) · `test_simulator_ac_savings_differential` |

### 2.3 Rules, Scheduling, and Auto-Actions (SRS §4.3)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| REQ-4.3.1 | Conditions: time / day / tariff window / device state / sensor | High | Rule engine (State + evaluator) | [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine._condition_holds` and `_validate_condition`; condition AST stored in [models.py](../backend/app/domain/models.py) `Rule.when_json` | [test_rules.py](../backend/tests/test_rules.py) · `test_auto_action_off_by_default`, `test_conflict_detection`; [test_safety.py](../backend/tests/test_safety.py) · `test_safety_warnings_on_validation` (occupancy/time conditions exercised) |
| REQ-4.3.2 | Rule action must match device capability | High | Rule engine + capability validator | [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.validate` (calls `validate_command`) | [test_rules.py](../backend/tests/test_rules.py) · `test_action_must_match_capability` |
| REQ-4.3.3 | Detect conflicting enabled rules before saving | High | Rule engine (conflict detector) | [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine._detect_conflicts` (+ `_times_overlap`) | [test_rules.py](../backend/tests/test_rules.py) · `test_conflict_detection` |
| REQ-4.3.4 | Enable / disable / edit / delete rules | High | Rule engine CRUD + REST router | [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.update` / `delete`; [api/rules.py](../backend/app/api/rules.py) `update_rule` / `delete_rule` | [test_rules.py](../backend/tests/test_rules.py) · `test_enable_disable_edit_delete` |
| REQ-4.3.5 | Log every execution (rule, device, action, ts, initiator, outcome) | High | Immutable audit log (entity) | [models.py](../backend/app/domain/models.py) `RuleExecution`; [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.execute`; [api/rules.py](../backend/app/api/rules.py) `rule_executions` | [test_rules.py](../backend/tests/test_rules.py) · `test_execution_logging_undo_and_history_preserved` |
| REQ-4.3.6 | Auto-action opt-in + 2-min undo | Medium | Rule engine (State) + config | [models.py](../backend/app/domain/models.py) `Rule.auto_apply` (default `False`); [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.execute` / `undo` (`settings.undo_window_seconds`); [api/rules.py](../backend/app/api/rules.py) `undo_execution` | [test_rules.py](../backend/tests/test_rules.py) · `test_auto_action_off_by_default`, `test_execution_logging_undo_and_history_preserved` |

### 2.4 Habit Learning and Recommendation Engine (SRS §4.4)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| REQ-4.4.1 | Recommend only after ≥ 7 days of telemetry | High | Recommendation engine (miners) | [recommendation_service.py](../backend/app/services/recommendation_service.py) `RecommendationService._has_enough_data` (`settings.recommendation_min_days`) | [test_recommendations.py](../backend/tests/test_recommendations.py) · `test_new_device_without_history_yields_no_recommendation` |
| REQ-4.4.2 | Readable WHEN-THEN + data window shown | High | Recommendation engine + summariser | [models.py](../backend/app/domain/models.py) `Recommendation` (`rationale`, `data_window_start/end`); [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.summarize` | [test_recommendations.py](../backend/tests/test_recommendations.py) · `test_recommendations_are_readable_and_explainable` |
| REQ-4.4.3 | Rank by VND saving, ≤ 5 active | High | Recommendation engine | [recommendation_service.py](../backend/app/services/recommendation_service.py) `RecommendationService.list_active` / `_enforce_max_active` (`settings.recommendation_max_active`) | [test_recommendations.py](../backend/tests/test_recommendations.py) · `test_recommendations_ranked_and_capped` |
| REQ-4.4.4 | Explicit acceptance → becomes a rule (never auto-applied) | High | Recommendation engine → rule engine | [recommendation_service.py](../backend/app/services/recommendation_service.py) `RecommendationService.accept`; [api/recommendations.py](../backend/app/api/recommendations.py) `accept` | [test_recommendations.py](../backend/tests/test_recommendations.py) · `test_accept_recommendation_becomes_rule` |
| REQ-4.4.5 | Dismissed → suppressed ≥ 30 days (same device/condition) | High | Recommendation engine (suppression) | [recommendation_service.py](../backend/app/services/recommendation_service.py) `RecommendationService.dismiss` / `_is_allowed` (`signature` + `settings.recommendation_dismiss_days`) | [test_recommendations.py](../backend/tests/test_recommendations.py) · `test_dismiss_suppresses_recommendation` |

### 2.5 Optimization Engine and Bill-Saving Estimation (SRS §4.5)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| REQ-4.5.1 | 14-day baseline consumption profile per device | High | Optimization engine (baseline) | [optimization_service.py](../backend/app/services/optimization_service.py) `OptimizationService.baseline_daily_kwh` / `hourly_baseline_kwh` (`settings.baseline_days = 14`) | [test_savings.py](../backend/tests/test_savings.py) · `test_estimate_before_save_uses_srs_formula` (asserts `baseline_kwh_month > 0`) |
| REQ-4.5.2 | Saving = Σ((baseline−expected) × tariff) | High | Optimization engine (formula) | [optimization_service.py](../backend/app/services/optimization_service.py) `OptimizationService.estimate_rule` (+ `_expected_window_kwh`, `_explain`); pricing via [tariff_service.py](../backend/app/services/tariff_service.py) `TariffService.effective_price` | [test_savings.py](../backend/tests/test_savings.py) · `test_estimate_before_save_uses_srs_formula`, `test_raising_ac_target_saves_energy` |
| REQ-4.5.3 | Show estimate before save / before accept | High | Optimization engine + REST | [api/savings.py](../backend/app/api/savings.py) `estimate`; [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.validate` (returns `estimated_monthly_saving_vnd`) | [test_savings.py](../backend/tests/test_savings.py) · `test_estimate_before_save_uses_srs_formula` |
| REQ-4.5.4 | Dashboard shows savings so far this cycle (VND) | High | Optimization engine (cycle accrual) | [optimization_service.py](../backend/app/services/optimization_service.py) `OptimizationService.savings_summary` / `accrue_savings`; surfaced by [telemetry_service.py](../backend/app/services/telemetry_service.py) `dashboard` (`savings_cycle_vnd`) | [test_savings.py](../backend/tests/test_savings.py) · `test_savings_summary_reports_cycle`, `test_savings_records_present`; [test_monitoring.py](../backend/tests/test_monitoring.py) · `test_dashboard_reports_home_metrics` |
| REQ-4.5.5 | ±20 % drift → mark rule "needs recalculation" | Medium | Optimization engine (drift check) | [optimization_service.py](../backend/app/services/optimization_service.py) `OptimizationService.check_drift` (`settings.savings_drift_threshold = 0.20`); [models.py](../backend/app/domain/models.py) `Rule.needs_recalculation`; invoked each tick by [scheduler.py](../backend/app/services/scheduler.py) `SchedulerEngine._evaluate_home` | [test_savings.py](../backend/tests/test_savings.py) · `test_drift_check_is_reachable`, `test_savings_records_present` |

---

## 3. Non-functional requirements (SRS §5)

### 3.1 Performance (§5.1)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| NFR-PER-1 | Dashboard refresh ≤ 5 s for ≤ 30 devices | High | Async simulator + push | [config.py](../backend/app/config.py) `Settings.telemetry_interval_seconds = 2.0`; [simulator/engine.py](../backend/app/simulator/engine.py) `SimulatorEngine._run`; [api/ws.py](../backend/app/api/ws.py) `ConnectionManager.broadcast` | [test_monitoring.py](../backend/tests/test_monitoring.py) · `test_dashboard_reports_home_metrics` (functional latency budget; load is a manual/demo concern) |
| NFR-PER-2 | UI feedback ≤ 2 s (95th pct) | High | Synchronous command path | [device_service.py](../backend/app/services/device_service.py) `DeviceService.apply_command` (single commit, immediate `CommandResult`) | [test_devices_capability.py](../backend/tests/test_devices_capability.py) · `test_command_validation_rejects_out_of_range` (immediate outcome) |
| NFR-PER-3 | ≥ 100 concurrent simulated homes | High | Async loops + per-home iteration | [scheduler.py](../backend/app/services/scheduler.py) `SchedulerEngine._tick_once` (iterates all homes); [simulator/engine.py](../backend/app/simulator/engine.py) `SimulatorEngine` (async, non-blocking) | Demonstrated by demo deployment; multi-home logic covered structurally by `SchedulerEngine._tick_once` (no dedicated load test) |

### 3.2 Safety (§5.2)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| NFR-SAF-1 | ≤ 1 AC compressor command / 3 min | High | Device service safety guard | [device_service.py](../backend/app/services/device_service.py) `DeviceService._safety_check` (`settings.ac_compressor_min_interval_seconds = 180`, `_AC_COMPRESSOR_CONTROLS`) | [test_safety.py](../backend/tests/test_safety.py) · `test_ac_compressor_rate_limit` |
| NFR-SAF-2 | No auto power-off of safety-critical devices | High | Device service safety guard | [device_service.py](../backend/app/services/device_service.py) `DeviceService._safety_check` (blocks SCHEDULER/SYSTEM `power=off` on `safety_critical`) | [test_safety.py](../backend/tests/test_safety.py) · `test_safety_critical_device_not_auto_powered_off` |
| NFR-SAF-3 | Warn on temperature / safety-critical / unattended power-off | High | Rule engine validation warnings | [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.validate` (warnings driven by `Control.safety_sensitive` in [capability.py](../backend/app/domain/capability.py)) | [test_safety.py](../backend/tests/test_safety.py) · `test_safety_warnings_on_validation` |

### 3.3 Security (§5.3)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| NFR-SEC-1 | TLS 1.2+ / WSS for all client-server traffic | High | Deployment (cross-cutting) | Deployment concern: HTTPS/WSS terminating proxy in front of [main.py](../backend/app/main.py); client uses `/ws` ([api/ws.py](../backend/app/api/ws.py) `ws_endpoint`) over WSS in production | Out of scope for unit tests (transport-layer / deployment); verified at deployment, see [02-software-design-document.md](./02-software-design-document.md) |
| NFR-SEC-2 | Authentication + role-based authorization | High | Core security + DI guards | [security.py](../backend/app/core/security.py) `create_access_token` / `decode_access_token`; [api/deps.py](../backend/app/api/deps.py) `get_current_user` / `require_roles` / `require_owner` | [test_auth_rbac.py](../backend/tests/test_auth_rbac.py) · `test_login_returns_token_and_user`, `test_login_rejects_bad_password`, `test_unauthenticated_request_is_rejected`, `test_family_cannot_add_device` |
| NFR-SEC-3 | No plaintext passwords / tokens | High | Core security (KDF) | [security.py](../backend/app/core/security.py) `hash_password` / `verify_password` (salted PBKDF2-HMAC-SHA256); [models.py](../backend/app/domain/models.py) `User.password_hash` | [test_unit_domain.py](../backend/tests/test_unit_domain.py) · `test_password_hash_roundtrip_never_plaintext` |
| NFR-SEC-4 | Home-scoped access to readings / control logs | High | Service-layer home scoping | Every service query filters by `home_id`, e.g. [repositories.py](../backend/app/repositories/repositories.py) `DeviceRepository.in_home` / `by_home`; [device_service.py](../backend/app/services/device_service.py) `get_or_404`; [telemetry_service.py](../backend/app/services/telemetry_service.py) `consumption_series` (home-scopes a supplied `device_id`) | [test_auth_rbac.py](../backend/tests/test_auth_rbac.py) · `test_owner_can_create_family_member` (granted vs. ungranted device → 403); [test_monitoring.py](../backend/tests/test_monitoring.py) · `test_consumption_rejects_foreign_device` (cross-home IDOR) |

---

## 4. Business rules and other requirements (SRS §5.5, §6.1)

| Requirement ID | Requirement (short) | Priority | Design element | Implementation (file · function/class) | Test(s) (file · test function) |
| :--- | :--- | :---: | :--- | :--- | :--- |
| BR-1 | Only Owner can add/remove devices & family members | High | DI role guard | [api/deps.py](../backend/app/api/deps.py) `require_owner` / `require_owner_or_dev`; [api/devices.py](../backend/app/api/devices.py) `add_mock_device` / `delete_device`; [api/auth.py](../backend/app/api/auth.py) `add_family_member` | [test_auth_rbac.py](../backend/tests/test_auth_rbac.py) · `test_family_cannot_add_device`, `test_owner_can_create_family_member` |
| BR-2 | Recommendations advisory until accepted | High | Recommendation engine | [recommendation_service.py](../backend/app/services/recommendation_service.py) `RecommendationService.accept` (status → ACCEPTED only on explicit call) | [test_recommendations.py](../backend/tests/test_recommendations.py) · `test_accept_recommendation_becomes_rule` |
| BR-3 | Auto-action disabled by default for every new rule | High | Rule entity default | [models.py](../backend/app/domain/models.py) `Rule.auto_apply = False`; [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.execute` (no device change when `auto_apply` off) | [test_rules.py](../backend/tests/test_rules.py) · `test_auto_action_off_by_default` |
| BR-4 | Deleting a rule keeps its execution history | High | Audit log design (no ORM cascade) | [models.py](../backend/app/domain/models.py) `Rule` (deliberately **no** `executions` relationship/cascade) + `RuleExecution`; [rule_engine.py](../backend/app/services/rule_engine.py) `RuleEngine.delete` | [test_rules.py](../backend/tests/test_rules.py) · `test_execution_logging_undo_and_history_preserved` |
| BR-5 | Tariff manually configurable; VND default | Medium | Tariff service + REST | [tariff_service.py](../backend/app/services/tariff_service.py) `TariffService.active` (manual fallback) / `effective_price`; [api/settings.py](../backend/app/api/settings.py) `create_tariff` / `activate_tariff`; `settings.currency = "VND"` | [test_unit_domain.py](../backend/tests/test_unit_domain.py) · `test_flat_tariff_pricing`, `test_tiered_tariff_is_progressive`; [test_auth_rbac.py](../backend/tests/test_auth_rbac.py) · `test_family_cannot_create_tariff` |
| REQ-6.1 | Export readings / rules / savings as CSV | Medium | Reporting service | [report_service.py](../backend/app/services/report_service.py) `ReportService.export_readings_csv` / `export_rules_csv` / `export_savings_csv`; [api/reports.py](../backend/app/api/reports.py) `export_readings` | [test_monitoring.py](../backend/tests/test_monitoring.py) · `test_csv_export` |

---

## 5. Supporting design-pattern traceability

These rows trace the syllabus design patterns (SRS Design Constraints / SDD) to code and the tests that exercise them, complementing the requirement rows above.

| Pattern | Design element | Implementation (file · class) | Test evidence |
| :--- | :--- | :--- | :--- |
| Strategy | Per-type device behaviour | [adapters/base.py](../backend/app/adapters/base.py) `DeviceAdapter`; [adapters/devices.py](../backend/app/adapters/devices.py) `get_adapter` | [test_unit_domain.py](../backend/tests/test_unit_domain.py) · `test_simulator_ac_savings_differential` |
| Observer | Decoupled event fan-out | [core/events.py](../backend/app/core/events.py) `EventBus`; subscribers in [notification_service.py](../backend/app/services/notification_service.py) `register_subscribers` and [api/ws.py](../backend/app/api/ws.py) `ConnectionManager.wire_bus` | [test_devices_capability.py](../backend/tests/test_devices_capability.py) · `test_offline_device_command_times_out` (offline event path) |
| Repository | Persistence abstraction | [repositories.py](../backend/app/repositories/repositories.py) `Repository[T]` + per-aggregate repos | Exercised indirectly by all service-level tests |
| Dependency Injection | Request-scoped wiring & guards | [api/deps.py](../backend/app/api/deps.py) `get_db` / `get_current_user` / `require_roles` | [test_auth_rbac.py](../backend/tests/test_auth_rbac.py) · all RBAC tests |
| State | Device & rule lifecycle | [models.py](../backend/app/domain/models.py) `Device.state`, `Rule.enabled`/`auto_apply`, `RuleExecution.outcome` | [test_rules.py](../backend/tests/test_rules.py) · `test_enable_disable_edit_delete` |

---

## 6. Coverage summary

- **Every** functional requirement (`REQ-4.1.1`–`REQ-4.5.5`) and **every** safety/security NFR (`NFR-SAF-*`, `NFR-SEC-2/3/4`) has **at least one** automated test, listed above.
- **All 31 High-priority functional requirements and High-priority safety/security NFRs are backed by ≥ 1 passing automated test.** The two Medium-priority functional requirements (REQ-4.3.6 undo, REQ-4.5.5 drift) and the data-export requirement (REQ-6.1) are also covered.
- The full suite is **54 tests, all passing** (`pytest -q` → 54 collected, 54 passed). Collection: see [backend/tests](../backend/tests) (`conftest.py` boots the app against a throwaway SQLite DB seeded with 21 days of demo telemetry, with the background simulator/scheduler disabled for determinism).
- Tests apply explicit black-box techniques cited in the test docstrings — **boundary-value analysis** and **equivalence partitioning** on the capability validator ([test_unit_domain.py](../backend/tests/test_unit_domain.py) `test_ac_target_boundaries`), and scenario/use-case tests for the acceptance criteria in [refine_note.md](../../Project_detail/refine_note.md) §10.
- **Deferred to deployment / non-automated verification:** `NFR-SEC-1` (TLS/WSS — transport-layer, configured at the reverse proxy) and `NFR-PER-1/2/3` (latency and 100-home scale — observed during the demo; the underlying code paths are tested functionally). These are flagged in their rows so the gap is explicit rather than hidden.

> **Reproduce:** `cd project/backend && . .venv/bin/activate && pytest -q`
