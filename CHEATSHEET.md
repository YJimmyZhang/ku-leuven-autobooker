# KU Leuven Autobooker — Cheatsheet

Quick reference for server, extension, and (fallback) tunnel diagnostics.

Replace placeholders with your values (see `config/local.env.example`):

| Placeholder | Your value |
|-------------|------------|
| `YOUR_DOMAIN` | HTTPS hostname, e.g. `yourname.duckdns.org` |
| `YOUR_SERVER_IP` | Droplet / VPS IP |
| `YOUR_SSH_KEY` | e.g. `~/.ssh/id_ed25519_do` |
| `YOUR_REPO` | Path to this project |

Cookies reach the server over **HTTPS** (primary — works on any network, no tunnel).
The **SSH tunnel is a fallback** for when you don't have HTTPS set up. See
`docs/HTTPS-SETUP.md` for the HTTPS setup.

---

## Daily use

| Task | What to do |
|------|------------|
| Send cookies | Open kurt3 in Firefox → **Send session to booker** (goes over HTTPS) |
| 18:00 booking | Automatic on server — laptop can be off |
| Tunnel | Not needed if HTTPS is set up; fallback only |

---

## Health checks

**Over HTTPS (primary):**

```bash
curl -s https://YOUR_DOMAIN/health | python3 -m json.tool | head -20
```

**Via tunnel (fallback, localhost):**

```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool | head -20
```

---

## Booking window (is booking active today?)

```bash
curl -s https://YOUR_DOMAIN/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('booking_active_today:', d.get('booking_active_today'))
print('status:', d.get('booking_status_message'))
"
```

---

## Firefox extension

1. `about:debugging` → **This Firefox** → **Load Temporary Add-on** → `extension/manifest.json`
2. Permissions: `about:addons` → extension → **Permissions** → enable listed hosts
3. After config change: **Remove** add-on → **Load** again (or **Reload**)

**Inspect console:** `about:debugging` → extension → **Inspect**

Success:

```
[Autobooker] ✓ Sent via https://YOUR_DOMAIN/update-cookie
```

(If it falls back to `http://127.0.0.1:8080/...`, the HTTPS endpoint was unreachable
and the tunnel handled it instead.)

---

## Server (SSH)

```bash
ssh -i YOUR_SSH_KEY root@YOUR_SERVER_IP
cd /opt/ku-leuven-autobooker/server
```

**App logs:**

```bash
docker compose logs -f --tail=30 autobooker
```

**Caddy / HTTPS logs (cert issuance, proxy errors):**

```bash
docker compose logs -f --tail=30 caddy
```

**After changing `.env` (must recreate, not just restart):**

```bash
docker compose up -d --force-recreate
```

**Check secret inside container:**

```bash
docker compose exec autobooker printenv SECRET_KEY
```

Must match `extension/relay-core.local.js` and `config/local.env`.

**Firewall (should show 80, 443, OpenSSH — NOT 8080):**

```bash
ufw status
```

---

## TLS certificate

Caddy obtains and renews the Let's Encrypt cert automatically. To check it from your Mac:

```bash
curl -vI https://YOUR_DOMAIN/health 2>&1 | grep -iE "subject:|issuer:|expire"
```

If you get a cert error right after first deploy, wait ~1 min (still issuing) and
retry. Let's Encrypt validates over **port 80**, so 80 must be open and DNS for
`YOUR_DOMAIN` must point at `YOUR_SERVER_IP`:

```bash
dig +short YOUR_DOMAIN   # must print YOUR_SERVER_IP
```

---

## SSH tunnel (fallback only)

Use this if you haven't set up HTTPS. Forwards the server's port to `localhost`,
which Firefox allows over plain http.

**Status:**

```bash
pgrep -fl "8080:127.0.0.1:8080"   # output = on, nothing = off
```

**Manual tunnel:**

```bash
cd YOUR_REPO
./scripts/tunnel.sh          # macOS / Linux — keep terminal open
.\scripts\tunnel.ps1         # Windows (PowerShell)
```

**Auto tunnel (install once):**

```bash
./scripts/install-tunnel-agent.sh    # macOS
.\scripts\install-tunnel-task.ps1    # Windows (PowerShell)
```

**Force run now / stop (macOS):**

```bash
launchctl kickstart -k "gui/$(id -u)/com.kuleuven.autobooker-tunnel"
pkill -f "8080:127.0.0.1:8080"
```

**Auto agent logs (macOS):**

```bash
cat ~/Library/Logs/ku-leuven-autobooker/tunnel.log
cat ~/Library/Logs/ku-leuven-autobooker/tunnel.err
```

---

## Common errors

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `timed out (8s)` / mixed-content to server IP in Firefox | Secure extension context can't reach plain `http://` public IP | Use the HTTPS endpoint (see `docs/HTTPS-SETUP.md`); tunnel as fallback |
| Cert error on `https://YOUR_DOMAIN` | Cert still issuing, port 80 closed, or DNS wrong | Wait 1 min; check `ufw status` (80 open) and `dig YOUR_DOMAIN` |
| `HTTP 401` | `SECRET_KEY` mismatch | Sync `.env` + `relay-core.local.js`, then `docker compose up -d --force-recreate` |
| `permissions.request may only be called from a user input handler` | Host permission not granted for an origin | Reload add-on; accept the host-permission prompt |
| `Address already in use` port 8080 | Tunnel already running | `pgrep -fl 8080` — don't start a second one |

---

## Secret files (never commit)

- `config/local.env`
- `extension/relay-core.local.js`
- `extension/manifest.json`
- `server/.env` (on server)

First-time setup: `./scripts/setup-local.sh`
