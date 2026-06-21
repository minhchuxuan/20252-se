#!/usr/bin/env bash
# Start / stop the public demo (backend :8000 + frontend :5173 + Cloudflare quick-tunnel).
# Usage:  bash demo.sh {start|stop|url|status}
#
# Stop is surgical: it kills only the process group this script started — never a
# broad pkill — so it cannot disturb anything else running on the machine.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG=/tmp/sheo_demo.log
PGF=/tmp/sheo_demo.pgid

_alive() { [ -f "$PGF" ] && kill -0 -- "-$(cat "$PGF")" 2>/dev/null; }

url() { grep -om1 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" 2>/dev/null || echo "(no public URL yet — check $LOG)"; }

start() {
  if _alive; then echo "Demo already running."; url; return 0; fi
  echo "Starting demo (backend :8000, frontend :5173, Cloudflare tunnel)…"
  setsid bash "$ROOT/share.sh" >"$LOG" 2>&1 </dev/null &
  local pid=$! pgid
  pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
  echo "${pgid:-$pid}" >"$PGF"
  printf "Waiting for the public URL"
  for _ in $(seq 1 30); do
    if grep -qm1 'trycloudflare\.com' "$LOG" 2>/dev/null; then echo; echo "Public URL:  $(url)"; return 0; fi
    printf "."; sleep 1
  done
  echo; echo "Timed out waiting for the tunnel. See $LOG"; return 1
}

stop() {
  if [ -f "$PGF" ]; then
    local pg; pg=$(cat "$PGF")
    if kill -- "-$pg" 2>/dev/null; then echo "Stopped demo (process group $pg)."; else echo "No live process group $pg (already stopped)."; fi
    rm -f "$PGF"
  else
    echo "No PID file ($PGF) — demo was not started by this script."
  fi
}

status() { if _alive; then echo "RUNNING — $(url)"; else echo "STOPPED"; fi; }

case "${1:-}" in
  start)  start ;;
  stop)   stop ;;
  url)    url ;;
  status) status ;;
  *) echo "Usage: bash demo.sh {start|stop|url|status}" ;;
esac
