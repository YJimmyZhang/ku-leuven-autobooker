#!/usr/bin/env bash
# Starts SSH tunnel only during the configured booking period.
# Used by the macOS LaunchAgent — safe to run when exams are over (exits immediately).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/local-env.sh
source "$SCRIPT_DIR/lib/local-env.sh"
load_local_env

DROPLET_IP="${DROPLET_IP:-${SERVER_IP:-YOUR_SERVER_IP}}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_do}"
LOCAL_PORT="${LOCAL_PORT:-8080}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOCAL_CONFIG="${LOCAL_CONFIG:-$SCRIPT_DIR/../config/booking.local.json}"
TUNNEL_PATTERN="127.0.0.1:${LOCAL_PORT}:127.0.0.1:8080"

tunnel_running() {
  pgrep -f "$TUNNEL_PATTERN" >/dev/null 2>&1
}

stop_tunnel() {
  if tunnel_running; then
    pkill -f "$TUNNEL_PATTERN" || true
    echo "[tunnel] Stopped (outside booking period or disabled)."
  fi
}

needs_tunnel() {
  local health
  if health=$(curl -sf --connect-timeout 4 "http://${DROPLET_IP}:8080/health" 2>/dev/null); then
    echo "$health" | python3 -c "
import json, sys
d = json.load(sys.stdin)
sys.exit(0 if d.get('booking_enabled') and d.get('booking_active_today') else 1)
"
    return $?
  fi

  if [[ -f "$LOCAL_CONFIG" ]]; then
    python3 - <<PY
import json, datetime
from pathlib import Path
c = json.loads(Path("$LOCAL_CONFIG").read_text())
if not c.get("booking_enabled", True):
    raise SystemExit(1)
today = datetime.date.today()
offset = datetime.timedelta(days=int(c.get("booking_date_offset_days", 8)))
start_s = c.get("booking_period_start") or "0000-01-01"
end_s = c.get("booking_period_end") or "9999-12-31"
seat_start = datetime.date.fromisoformat(start_s[:10])
seat_end = datetime.date.fromisoformat(end_s[:10])
run_start = seat_start - offset
run_end = seat_end - offset
raise SystemExit(0 if run_start <= today <= run_end else 1)
PY
    return $?
  fi

  return 1
}

start_tunnel() {
  if tunnel_running; then
    echo "[tunnel] Already running on localhost:${LOCAL_PORT}"
    return 0
  fi
  echo "[tunnel] Starting → localhost:${LOCAL_PORT} (booking period active)"
  ssh -i "$SSH_KEY" -f -N \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    -L "${LOCAL_PORT}:127.0.0.1:8080" \
    "root@${DROPLET_IP}"
}

if needs_tunnel; then
  start_tunnel
else
  stop_tunnel
  echo "[tunnel] Not needed today — booking period inactive or disabled."
fi
