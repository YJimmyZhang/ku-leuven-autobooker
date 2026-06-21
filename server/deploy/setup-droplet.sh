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

echo "==> Opening port 8080 in UFW..."
ufw allow OpenSSH
ufw allow 8080/tcp
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
  echo "IMPORTANT: Edit $APP_DIR/server/.env and set SECRET_KEY"
  echo "  nano $APP_DIR/server/.env"
  exit 1
fi

echo "==> Starting autobooker..."
docker compose up -d --build

echo ""
echo "Done. Server should be live at:"
echo "  http://$(curl -s ifconfig.me):8080/health"
echo ""
echo "Update extension/background.js:"
echo "  WEBHOOK_URL = \"http://YOUR_DROPLET_IP:8080/update-cookie\""
echo "  SECRET_KEY  = (same value as in .env)"
