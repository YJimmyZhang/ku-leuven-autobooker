#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/local-env.sh
source "$SCRIPT_DIR/lib/local-env.sh"
load_local_env

OUT="$SCRIPT_DIR/../config/booking.local.json"
DROPLET_IP="${DROPLET_IP:-${SERVER_IP:-YOUR_SERVER_IP}}"

if ! health=$(curl -sf --connect-timeout 4 "http://${DROPLET_IP}:8080/health" 2>/dev/null || curl -sf --connect-timeout 2 "http://127.0.0.1:8080/health" 2>/dev/null); then
  echo "Could not reach server /health" >&2
  exit 1
fi

echo "$health" | python3 -c "
import json, sys
from pathlib import Path
d = json.load(sys.stdin)
out = {
    'booking_enabled': d.get('booking_enabled', True),
    'booking_period_start': (d.get('booking_period_start') or (d.get('booking_period') or {}).get('start') or '')[:10],
    'booking_period_end': (d.get('booking_period_end') or (d.get('booking_period') or {}).get('end') or '')[:10],
}
Path(sys.argv[1]).write_text(json.dumps(out, indent=2) + '\n')
print('Wrote', sys.argv[1])
" "$OUT"
