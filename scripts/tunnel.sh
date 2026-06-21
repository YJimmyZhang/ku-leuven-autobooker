#!/usr/bin/env bash
# Forward droplet port 8080 to your Mac so the Firefox extension can reach it on KU WiFi.
# Keep this terminal open while sending cookies. Booking at 18:00 still runs on the droplet.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/local-env.sh
source "$SCRIPT_DIR/lib/local-env.sh"
load_local_env

DROPLET_IP="${DROPLET_IP:-${SERVER_IP:-YOUR_SERVER_IP}}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_do}"

exec ssh -i "$SSH_KEY" -N -L 8080:127.0.0.1:8080 "root@${DROPLET_IP}"
