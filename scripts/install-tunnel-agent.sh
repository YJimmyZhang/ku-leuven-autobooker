#!/usr/bin/env bash
# Install macOS LaunchAgent: checks every 30 min and during booking period only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TUNNEL_SCRIPT="$SCRIPT_DIR/tunnel-if-needed.sh"
PLIST="$HOME/Library/LaunchAgents/com.kuleuven.autobooker-tunnel.plist"
LOG_DIR="$HOME/Library/Logs/ku-leuven-autobooker"

chmod +x "$TUNNEL_SCRIPT"

mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.kuleuven.autobooker-tunnel</string>
  <key>ProgramArguments</key>
  <array>
    <string>${TUNNEL_SCRIPT}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>1800</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/tunnel.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/tunnel.err</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/com.kuleuven.autobooker-tunnel" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/com.kuleuven.autobooker-tunnel"
launchctl kickstart -k "gui/$(id -u)/com.kuleuven.autobooker-tunnel"

echo "Installed LaunchAgent."
echo "  Logs: $LOG_DIR/tunnel.log"
echo "  Runs at login + every 30 min"
echo "  Tunnel only when booking period is active (checks server /health)"
echo ""
echo "Open settings UI (with tunnel): http://127.0.0.1:8080/admin"
