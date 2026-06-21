#!/usr/bin/env bash
# One-time local setup: copy example config files (real values stay gitignored).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

copy_if_missing() {
  local src="$1" dest="$2"
  if [[ -f "$dest" ]]; then
    echo "  keep  $dest"
  else
    cp "$src" "$dest"
    echo "  create $dest  (edit this file)"
  fi
}

echo "==> Local config (not pushed to git)"
copy_if_missing config/local.env.example config/local.env
copy_if_missing extension/relay-core.local.js.example extension/relay-core.local.js
copy_if_missing extension/manifest.json.example extension/manifest.json

echo ""
echo "Next:"
echo "  1. Edit config/local.env"
echo "  2. Edit extension/relay-core.local.js (SECRET_KEY must match server/.env)"
echo "  3. Edit extension/manifest.json — set YOUR_SERVER_IP in host_permissions"
echo "  4. On droplet: server/.env with same SECRET_KEY"
echo "  5. Firefox → about:debugging → Load Temporary Add-on → extension/manifest.json"
