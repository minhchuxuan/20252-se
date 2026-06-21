# Frontend — AI-Driven Smart Home Energy Optimizer

React 18 + Vite single-page app that forms the presentation tier. See the full
project [README](../README.md) and the SE deliverables under [../docs](../docs).

## Pages

Routing lives in [`src/App.jsx`](src/App.jsx); when no user is authenticated the
app renders [`Login`](src/pages/Login.jsx), otherwise the routed pages inside
[`Layout`](src/components/Layout.jsx):

- **Dashboard** ([`pages/Dashboard.jsx`](src/pages/Dashboard.jsx)) — BAN tiles
  (current kW, today kWh, estimated bill, savings this cycle), a live area chart,
  and device tiles; instantaneous power streams in over WebSocket (REQ-4.1.x,
  REQ-4.5.4).
- **Devices** ([`pages/Devices.jsx`](src/pages/Devices.jsx)) — device list,
  capability-driven control modal, add-mock-device, and the connectivity toggle
  to force a device offline (REQ-4.2.x, REQ-4.1.4).
- **Rules** ([`pages/Rules.jsx`](src/pages/Rules.jsx)) — WHEN-THEN editor with
  conflict detection and a VND estimate shown *before* saving, auto-action
  opt-in, and the 2-minute undo (REQ-4.3.x, REQ-4.5.3).
- **Recommendations** ([`pages/Recommendations.jsx`](src/pages/Recommendations.jsx))
  — Analyze, explainable cards (VND hero + WHEN→THEN + rationale + data window),
  Accept→rule, Dismiss (REQ-4.4.x).
- **Reports** ([`pages/Reports.jsx`](src/pages/Reports.jsx)) — consumption
  history, top consumers, and CSV export (REQ-4.1.2, REQ-4.1.5, §6.1).
- **Settings** ([`pages/Settings.jsx`](src/pages/Settings.jsx)) — tariff
  configuration, family members, preferences (owner-only mutations).

Shared building blocks: [`api/client.js`](src/api/client.js) (REST),
[`api/ws.js`](src/api/ws.js) (`useLiveFeed` WebSocket hook),
[`auth/AuthContext.jsx`](src/auth/AuthContext.jsx),
[`components/ui.jsx`](src/components/ui.jsx) (BAN / Pill / Modal), and
[`lib/format.js`](src/lib/format.js) (VND/kWh formatting + Okabe–Ito
colourblind-safe palette in [`index.css`](src/index.css)).

## Capability-driven controls

There are **no per-device-model screens**.
[`components/DeviceControl.jsx`](src/components/DeviceControl.jsx) fetches the
device's schema from `GET /api/devices/{id}/capabilities` and renders each
control from its declared `kind` (toggle / range / enum) and bounds. The same
schema is what the backend validates commands against, so the UI and the
contract can never drift. Adding a new device type requires no frontend change.

## Run / build

```bash
npm install
npm run dev      # Vite dev server on http://localhost:5173
npm run build    # production build to dist/
npm run preview  # preview the production build
```

## Dev proxy

[`vite.config.js`](vite.config.js) proxies `/api` (HTTP) and `/ws` (WebSocket)
to the backend at `127.0.0.1:8000`, so the app uses same-origin relative URLs in
development. **Start the backend first** (see [../backend/README.md](../backend/README.md)),
then log in with a demo account (`admin@demo.com` / `resident@demo.com` /
`dev@demo.com`, password `demo1234`).
