# Backend — AI-Driven Smart Home Energy Optimizer

FastAPI service (Python 3.13) implementing the application + data tiers and the
device-behaviour mock. See the full project [README](../README.md) and the SE
deliverables under [../docs](../docs).

## Layered architecture

A layered backend behind the presentation tier, dependencies pointing inward:

- **API (presentation)** — [`app/api/`](app/api): FastAPI routers, the WebSocket
  endpoint, and Dependency-Injection helpers ([`deps.py`](app/api/deps.py):
  `get_db`, `get_current_user`, `require_roles` / `require_owner` /
  `require_owner_or_dev`).
- **Services (application)** — [`app/services/`](app/services): business logic
  (auth, device, telemetry, rule_engine, scheduler, recommendation,
  optimization, notification, tariff, report).
- **Repositories (data access)** — [`app/repositories/repositories.py`](app/repositories/repositories.py):
  generic `Repository[T]` + per-aggregate repos over SQLAlchemy.
- **Domain** — [`app/domain/`](app/domain): `enums.py`, the declarative
  `capability.py` schema (drives the UI *and* validates commands),
  `models.py` (ORM aggregates).
- **Core (cross-cutting)** — [`app/core/`](app/core): `security.py`
  (JWT + PBKDF2-HMAC-SHA256 salted hash), `events.py` (Observer `EventBus`),
  `clock.py`, `errors.py`, `timeutil.py`.
- **Adapters & simulator** — [`app/adapters/`](app/adapters) (Strategy:
  per-type device adapters via `get_adapter()`) and
  [`app/simulator/`](app/simulator) (mock world + telemetry engine).

[`app/main.py`](app/main.py) is the app factory: its lifespan runs
`init_db → seed → wire Observers → start simulator + scheduler`, and maps
`DomainError` to HTTP responses.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

On first start it seeds 21 days of demo data. Interactive API docs:
`http://127.0.0.1:8000/docs`; health check: `GET /api/health`.

Demo accounts (password `demo1234`): `admin@demo.com`, `resident@demo.com`,
`resident2@demo.com`, `dev@demo.com`.

## Test

```bash
pytest
```

54 tests across `tests/` (domain/capability/security units, RBAC, monitoring,
rules, recommendations, savings, safety). Tests run with the background loops
disabled via the `enable_background` setting in [conftest.py](tests/conftest.py).

## Environment variables

All tunables live in [`app/config.py`](app/config.py) (Pydantic Settings,
env prefix **`SHEO_`**, optional `.env`). Defaults shown; override e.g.
`SHEO_DATABASE_URL=...`.

| Variable | Default | SRS link |
| :--- | :--- | :--- |
| `SHEO_DATABASE_URL` | `sqlite:///./sheo.db` | persistence |
| `SHEO_JWT_SECRET` | `dev-only-secret-change-in-production` | NFR-SEC-3 |
| `SHEO_JWT_ALGORITHM` | `HS256` | NFR-SEC |
| `SHEO_ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | NFR-SEC |
| `SHEO_TELEMETRY_INTERVAL_SECONDS` | `2.0` | REQ-4.1.1 (≤5 s) |
| `SHEO_OFFLINE_THRESHOLD_SECONDS` | `60` | REQ-4.1.4 |
| `SHEO_READING_RETENTION_DAYS` | `365` | REQ-4.1.3 (≥12 mo) |
| `SHEO_BASELINE_DAYS` | `14` | REQ-4.5.1 |
| `SHEO_SAVINGS_DRIFT_THRESHOLD` | `0.20` | REQ-4.5.5 (±20%) |
| `SHEO_DEFAULT_TARIFF_VND_PER_KWH` | `2500.0` | tariff fallback |
| `SHEO_RECOMMENDATION_MIN_DAYS` | `7` | REQ-4.4.1 |
| `SHEO_RECOMMENDATION_MAX_ACTIVE` | `5` | REQ-4.4.3 |
| `SHEO_RECOMMENDATION_DISMISS_DAYS` | `30` | REQ-4.4.5 |
| `SHEO_UNDO_WINDOW_SECONDS` | `120` | REQ-4.3.6 (2 min) |
| `SHEO_AC_COMPRESSOR_MIN_INTERVAL_SECONDS` | `180` | NFR-SAF-1 (3 min) |
| `SHEO_CURRENCY` / `SHEO_DEFAULT_LOCALE` | `VND` / `vi` | §6.2 |
| `SHEO_SEED_HISTORY_DAYS` | `21` | demo seed |
| `SHEO_SEED_ON_STARTUP` | `true` | demo seed |
| `SHEO_ENABLE_BACKGROUND` | `true` | simulator + scheduler |
| `SHEO_CORS_ORIGINS` | dev Vite origins | frontend dev |

## Key endpoints

All under `/api` (JWT bearer required except `/auth/register`, `/auth/login`,
`/api/health`). Full schemas at `/docs`.

- **Auth** — `POST /api/auth/register`, `POST /api/auth/login`,
  `GET /api/auth/me`, `POST /api/auth/residents` (admin-only).
- **Devices** — `GET /api/devices`, `GET /api/devices/profiles/mock`,
  `POST /api/devices`, `GET /api/devices/{id}`, `DELETE /api/devices/{id}`,
  `GET /api/devices/{id}/capabilities`, `POST /api/devices/{id}/command`,
  `POST /api/devices/{id}/connectivity`.
- **Monitoring** — `GET /api/dashboard`, `GET /api/consumption`,
  `GET /api/top-consumers`.
- **Rules** — `GET /api/rules`, `POST /api/rules/validate`, `POST /api/rules`,
  `GET /api/rules/{id}`, `PATCH /api/rules/{id}`, `DELETE /api/rules/{id}`,
  `GET /api/rules/{id}/executions`, `POST /api/executions/{id}/undo`.
- **Recommendations** — `GET /api/recommendations`,
  `POST /api/recommendations/analyze`,
  `POST /api/recommendations/{id}/accept`,
  `POST /api/recommendations/{id}/dismiss`.
- **Savings** — `GET /api/savings/summary`, `GET /api/savings/records`,
  `POST /api/savings/estimate`.
- **Reports** — `GET /api/reports/export/readings.csv`,
  `GET /api/reports/export/rules.csv`, `GET /api/reports/export/savings.csv`.
- **Settings** — `GET /api/settings`, `GET /api/tariffs`, `POST /api/tariffs`
  (admin-only), `PUT /api/tariffs/{id}/activate` (admin-only),
  `GET /api/notifications`, `POST /api/notifications/{id}/read`,
  `POST /api/notifications/read-all`.
- **WebSocket** — `GET /ws?token=<jwt>` for live telemetry and event push.
