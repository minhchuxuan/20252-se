#!/usr/bin/env bash
# One-command public share: boots the FastAPI backend, the Vite frontend, and a
# Cloudflare quick tunnel, then prints the public https URL friends can open.
# Equivalent to Gradio's `--share`, for this two-process stack.
#
# Only the single Vite port (5173) is tunnelled; Vite proxies /api and /ws to the
# backend locally, so the whole app is reachable through the one public URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUDFLARED="$ROOT/.bin/cloudflared"

pids=()
cleanup() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM   # only kills the children THIS script started

echo "==> starting backend (uvicorn :8000)"
( cd "$ROOT/backend" && .venv/bin/python -m uvicorn app.main:app --port 8000 ) &
pids+=($!)

echo "==> starting frontend (vite :5173)"
( cd "$ROOT/frontend" && npm run dev -- --host ) &
pids+=($!)

sleep 4
echo "==> opening Cloudflare tunnel — public URL appears below"
"$CLOUDFLARED" tunnel --url http://localhost:5173
