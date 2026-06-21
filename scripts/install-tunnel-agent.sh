#!/usr/bin/env bash
# Install macOS LaunchAgent: checks every 30 min and during booking period only.
#
# macOS blocks LaunchAgents from executing scripts in ~/Documents. We install a
# copy under ~/Library/Application Support/ and run that instead.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
AGENT_DIR="$HOME/Library/Application Support/ku-leuven-autobooker"
AGENT_BIN="$AGENT_DIR/tunnel-if-needed.sh"
AGENT_LIB="$AGENT_DIR/lib/local-env.sh"
AGENT_RUN="$AGENT_DIR/run-tunnel.sh"
PLIST="$HOME/Library/LaunchAgents/com.kuleuven.autobooker-tunnel.plist"
LOG_DIR="$HOME/Library/Logs/ku-leuven-autobooker"

chmod +x "$SCRIPT_DIR/tunnel-if-needed.sh" "$SCRIPT_DIR/tunnel.sh"

mkdir -p "$AGENT_DIR/lib" "$LOG_DIR" "$HOME/Library/LaunchAgents"
cp "$SCRIPT_DIR/tunnel-if-needed.sh" "$AGENT_BIN"
cp "$SCRIPT_DIR/lib/local-env.sh" "$AGENT_LIB"
chmod +x "$AGENT_BIN"

if [[ -f "$REPO_ROOT/config/local.env" ]]; then
  cp "$REPO_ROOT/config/local.env" "$AGENT_DIR/local.env"
else
  echo "Warning: config/local.env not found — copy config/local.env.example first." >&2
fi

if [[ -f "$REPO_ROOT/config/booking.local.json" ]]; then
  cp "$REPO_ROOT/config/booking.local.json" "$AGENT_DIR/booking.local.json"
fi

cat > "$AGENT_RUN" <<'EOF'
#!/bin/bash
export AUTBOOKER_AGENT_DIR="$HOME/Library/Application Support/ku-leuven-autobooker"
exec /bin/bash "$AUTBOOKER_AGENT_DIR/tunnel-if-needed.sh"
EOF
chmod +x "$AGENT_RUN"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.kuleuven.autobooker-tunnel</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${AGENT_RUN}</string>
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
echo "  Agent files: $AGENT_DIR"
echo "  Logs: $LOG_DIR/tunnel.log"
echo "  Runs at login + every 30 min"
echo "  Tunnel only when booking period is active (checks server /health)"
echo ""
echo "After editing config/local.env, re-run this script to refresh the agent copy."
echo "Open settings UI (with tunnel): http://127.0.0.1:8080/admin"
