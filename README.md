# AI-Driven Smart Home Energy Optimizer

A web application that monitors a household's electricity consumption, controls
supported smart devices through a declarative **capability schema**, and turns
detected usage habits into **explainable WHEN-THEN rules** with savings shown in
**VND**. Built for IT3180E (Introduction to Software Engineering, HUST/SOICT) as
a software-engineering exercise: the emphasis is on requirements→design→code→test
traceability, a layered three-tier architecture, named design patterns, and
verification — not on ML. The "AI" is deterministic and rule-based, and a
**mock device simulator** stands in for real IoT hardware so the whole system is
demoable and testable without any physical devices.

## Features (mapped to the SRS)

| Feature | SRS | What it does |
| :--- | :--- | :--- |
| Real-time energy monitoring | §4.1 (REQ-4.1.1–4.1.5) | Live per-device watts (≤5 s refresh over WebSocket), cumulative kWh for today / cycle / range, 1-minute aggregates retained ≥12 months, offline detection after 60 s, top-3 consumers. |
| Capability-driven device control | §4.2 (REQ-4.2.1–4.2.5) | `GET /api/devices/{id}/capabilities` drives the control UI; commands validated against declared ranges; success/rejected/timeout outcomes; mock plug/bulb/fan/AC/sensor profiles. |
| Rules, scheduling & auto-actions | §4.3 (REQ-4.3.1–4.3.6) | WHEN-THEN rules over time/day/tariff/device-state/occupancy; conflict detection; execution log; auto-action opt-in with a 2-minute undo. |
| Habit learning & recommendations | §4.4 (REQ-4.4.1–4.4.5) | Recommendations from ≥7 days of telemetry, expressed as readable WHEN-THEN with the data window, ranked by VND, ≤5 active, explicit accept→rule, dismissed for ≥30 days. |
| Optimization & bill-saving estimate | §4.5 (REQ-4.5.1–4.5.5) | 14-day baseline, VND savings estimate shown *before* saving a rule, cycle-to-date savings on the dashboard, ±20% drift flag. |
| Safety & security | §5.2–5.3 | ≤1 AC compressor command / 3 min, no auto power-off of safety-critical devices, rule warnings; JWT auth, role-based access, salted-hash passwords, home-scoped queries. |
| Reports & export | §6.1 | Consumption history, top consumers, CSV export of readings / rules / savings. |

## Tech stack

**Backend:** Python 3.13 · FastAPI · SQLAlchemy 2.0 · SQLite · Pydantic v2 · PyJWT · Uvicorn —
**Frontend:** React 18 · Vite · react-router-dom · Recharts · WebSocket live updates.

## Quick start

The backend seeds **21 days of demo data on first start** (one home, three users,
a tiered EVN tariff, six devices, history with detectable waste, one accepted
auto-rule with measured savings, and generated recommendations), so the app is
fully populated the moment you open it.

### 1. Backend (FastAPI on `:8000`)

```bash
cd project/backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs are then available at `http://127.0.0.1:8000/docs`, health at
`http://127.0.0.1:8000/api/health`.

### 2. Frontend (Vite dev server on `:5173`)

```bash
cd project/frontend
npm install
npm run dev
```

Vite proxies `/api` and `/ws` to `127.0.0.1:8000`, so start the backend first.

### Demo accounts (password `demo1234`)

The deployment models **one apartment building**. The Administrator is the building
owner (no unit of their own); each Resident is the tenant of one unit with its own
devices.

| Email | Role | Can |
| :--- | :--- | :--- |
| `admin@demo.com` | Administrator (building owner) | Monitor the **building overview** across every unit (roster, per-unit power/bill, totals), set the **building-wide tariff**, and **sell units / onboard residents**. Does **not** operate any unit's devices. |
| `resident@demo.com` | Resident — **Unit 101** | Operate every device in their own unit and view their unit dashboard, rules, recommendations and reports. |
| `resident2@demo.com` | Resident — **Unit 102** | A second, independent unit; cannot see or touch Unit 101 (cross-unit isolation, NFR-SEC-4). |
| `dev@demo.com` | Developer / Tester — maintenance **Unit 100** | Maintainer: add/manage mock devices, operate devices for diagnostics, run acceptance flows. |

## How to demo

### As the Administrator (building owner) — `admin@demo.com`

1. **Building overview** — the roster of units with each unit's live load, kWh this
   cycle, projected bill, and online-device count, plus building-wide totals.
   **View** any unit to drill into its dashboard and device list **read-only**
   (the owner monitors but never operates a unit's devices, NFR-SEC-2).
2. **Settings** — set the **building-wide tariff** (tiered EVN structure) and
   **sell a unit**: onboarding a resident creates a new unit pre-fitted with the
   default device package (Business Rule, NFR-SEC-2).

### As a Resident (tenant) — `resident@demo.com`

3. **Dashboard** — BAN tiles (current kW, today's kWh, estimated bill, savings this
   cycle) and a live area chart updating over WebSocket (REQ-4.1.1, REQ-4.5.4).
4. **Devices** — open a device to see controls *rendered from its capability schema*.
   Change the **Bedroom AC** target and the **Living Room Fan** speed; values are
   validated against the schema before the command is sent (REQ-4.2.1–4.2.3).
5. **Rules** — build *WHEN time is 23:00 THEN turn off the Living Room TV Plug*; see
   the **conflict check** and **VND estimate** before saving (REQ-4.3.3, REQ-4.5.3),
   enable **auto-action** (off by default), let it fire, then **Undo** within the
   2-minute window (REQ-4.3.6).
6. **Recommendations** — click **Analyze**; each card leads with the green VND/month
   figure, the WHEN→THEN summary, the rationale and the data window (REQ-4.4.2–4.4.3).
   **Accept** one and watch it become a rule (REQ-4.4.4). The fridge plug is never
   recommended off (NFR-SAF-2).
7. **Reports** — switch ranges, see the **top consumers**, and **export CSV**
   (REQ-4.1.5, §6.1). Logging in as the Developer (`dev@demo.com`) additionally
   exposes the **force-offline** connectivity hook on a device (REQ-4.1.4, REQ-4.2.4).

## Where each SRS requirement lives

A compact pointer; the full clause-by-clause matrix is in
[docs/03-requirements-traceability-matrix.md](docs/03-requirements-traceability-matrix.md).

| REQ group | Main implementation files |
| :--- | :--- |
| §4.1 Monitoring | [telemetry_service.py](backend/app/services/telemetry_service.py), [simulator/engine.py](backend/app/simulator/engine.py), [api/ws.py](backend/app/api/ws.py), [api/monitoring.py](backend/app/api/monitoring.py) |
| §4.2 Capability & control | [domain/capability.py](backend/app/domain/capability.py), [device_service.py](backend/app/services/device_service.py), [adapters/devices.py](backend/app/adapters/devices.py), [DeviceControl.jsx](frontend/src/components/DeviceControl.jsx) |
| §4.3 Rules & auto-actions | [rule_engine.py](backend/app/services/rule_engine.py), [scheduler.py](backend/app/services/scheduler.py), [api/rules.py](backend/app/api/rules.py) |
| §4.4 Recommendations | [recommendation_service.py](backend/app/services/recommendation_service.py), [api/recommendations.py](backend/app/api/recommendations.py) |
| §4.5 Optimization & savings | [optimization_service.py](backend/app/services/optimization_service.py), [api/savings.py](backend/app/api/savings.py) |
| §5.2 Safety | [device_service.py](backend/app/services/device_service.py) (`_safety_check`), [config.py](backend/app/config.py) |
| §5.3 Security & RBAC | [core/security.py](backend/app/core/security.py), [api/deps.py](backend/app/api/deps.py) |
| §6.1 Export | [report_service.py](backend/app/services/report_service.py), [api/reports.py](backend/app/api/reports.py) |

## Documentation

Software-engineering deliverables live under [`docs/`](docs/):

- [docs/01-feasibility-study.md](docs/01-feasibility-study.md) — scope, benefits, technical feasibility, risks, schedule.
- [docs/02-software-design-document.md](docs/02-software-design-document.md) — three-tier + layered architecture, the six UML diagram types (use-case, class, component, deployment, sequence, state) in Mermaid, and the design patterns (Strategy, Observer, State, Repository, Dependency Injection).
- [docs/03-requirements-traceability-matrix.md](docs/03-requirements-traceability-matrix.md) — every REQ/NFR → design → code → test.
- [docs/04-test-plan.md](docs/04-test-plan.md) — test plan & report, test levels, black-box techniques, acceptance mapping, V&V.
- [docs/05-configuration-management-plan.md](docs/05-configuration-management-plan.md) — SCIs, version control, baselines, change control, build & release.

## Tests

```bash
cd project/backend
pytest
```

54 tests, all passing — unit (domain, capability, security), RBAC, monitoring,
rules, recommendations, savings, and safety. See
[docs/04-test-plan.md](docs/04-test-plan.md).

## Project structure

```
project/
├── README.md
├── docs/                       # SE deliverables (feasibility, SDD+UML, RTM, test plan, CM plan)
├── backend/                    # FastAPI application (Python 3.13)
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py             # app factory + lifespan (init_db → seed → simulator/scheduler)
│   │   ├── config.py           # all SRS policy thresholds (env-overridable, SHEO_ prefix)
│   │   ├── database.py
│   │   ├── seed.py             # demo home, 3 users, tariff, 6 devices, 21-day history
│   │   ├── domain/             # enums, capability schema, ORM models
│   │   ├── core/               # security (JWT/PBKDF2), EventBus, clock, errors, timeutil
│   │   ├── adapters/           # Strategy: per-type device adapters
│   │   ├── simulator/          # mock world + telemetry engine
│   │   ├── repositories/       # Repository pattern over SQLAlchemy
│   │   ├── schemas/            # Pydantic DTOs
│   │   ├── services/           # business logic (application tier)
│   │   └── api/                # FastAPI routers + DI deps + WebSocket
│   └── tests/                  # 54 pytest tests
└── frontend/                   # React 18 + Vite SPA
    ├── package.json
    ├── vite.config.js          # dev proxy: /api, /ws → 127.0.0.1:8000
    └── src/
        ├── App.jsx             # routing
        ├── api/                # REST client + WebSocket hook
        ├── auth/               # AuthContext
        ├── components/         # Layout, ui (BAN/Pill/Modal), DeviceControl (capability-driven)
        ├── lib/                # formatting + colourblind-safe palette
        └── pages/              # Login, Dashboard, Devices, Rules, Recommendations, Reports, Settings
```

## What is mocked / deferred

- **No real hardware.** A background mock simulator
  ([simulator/engine.py](backend/app/simulator/engine.py)) generates telemetry
  and a scheduler runs the rules; every device speaks through the same adapter
  interface a real vendor adapter would (SRS §2.1 says firmware is out of scope).
- **Explainable, rule-based "AI."** Recommendations are produced by a
  deterministic habit miner and always rendered as readable WHEN-THEN rules with
  their data window — no opaque model (SRS §2.5 constraint).
- **SQLite + single-process background loops** keep the project self-contained
  for a class demo; TLS/WSS, push notifications (APNs/FCM), MQTT transport, and
  multi-home scale-out are deployment concerns noted in the SRS but not built.
