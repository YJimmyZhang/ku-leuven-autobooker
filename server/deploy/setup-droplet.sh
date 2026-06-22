#!/usr/bin/env bash
# Run on a fresh Ubuntu 24.04 DigitalOcean droplet in Amsterdam (ams3).
set -euo pipefail

APP_DIR="/opt/ku-leuven-autobooker"

echo "==> Installing Docker..."
apt-get update
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

echo "==> Opening ports 80 + 443 in UFW (for Caddy / HTTPS)..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
# Port 8080 is intentionally NOT opened: the app binds to 127.0.0.1 only and is
# reached either via Caddy (HTTPS) or the SSH tunnel. Close it if it was opened before.
ufw delete allow 8080/tcp 2>/dev/null || true
ufw --force enable

echo "==> Cloning app (or skip if you upload files manually)..."
mkdir -p "$APP_DIR"
if [ ! -f "$APP_DIR/server/app.py" ]; then
  echo "Place your project in $APP_DIR before continuing."
  echo "Example from your Mac:"
  echo "  rsync -avz --exclude .venv --exclude cookie_store.json \\"
  echo "    ./server/ root@YOUR_DROPLET_IP:$APP_DIR/server/"
  exit 1
fi

cd "$APP_DIR/server"

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "IMPORTANT: Edit $APP_DIR/server/.env and set SECRET_KEY and DOMAIN"
  echo "  nano $APP_DIR/server/.env"
  exit 1
fi

# DOMAIN must be set for Caddy to obtain a TLS certificate.
set -a; . ./.env; set +a
if [ -z "${DOMAIN:-}" ] || [ "${DOMAIN}" = "yourname.duckdns.org" ]; then
  echo "ERROR: Set DOMAIN in $APP_DIR/server/.env to your real hostname first."
  echo "  Create a free one at https://www.duckdns.org and point it at this droplet's IP."
  exit 1
fi

echo "==> Starting autobooker + Caddy (auto-HTTPS for ${DOMAIN})..."
docker compose up -d --build

echo ""
echo "Done. Once DNS for ${DOMAIN} points here, the server is live at:"
echo "  https://${DOMAIN}/health"
echo ""
echo "Caddy fetches the TLS cert on first request — give it ~30s, then test the URL above."
echo ""
echo "Point the Firefox extension at it (extension/relay-core.local.js):"
echo "  WEBHOOK_URLS first entry = \"https://${DOMAIN}/update-cookie\""
echo "  SECRET_KEY               = (same value as in .env)"
