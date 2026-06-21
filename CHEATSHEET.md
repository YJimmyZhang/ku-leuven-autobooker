# KU Leuven Autobooker — Cheatsheet

Quick reference for tunnel, extension, and server diagnostics.

Replace placeholders with your values (see `config/local.env.example`):

| Placeholder | Your value |
|-------------|------------|
| `YOUR_SERVER_IP` | Droplet / VPS IP |
| `YOUR_SSH_KEY` | e.g. `~/.ssh/id_ed25519_do` |
| `YOUR_REPO` | Path to this project |

---

## Daily use

| Task | What to do |
|------|------------|
| Send cookies (on campus) | Open kurt3 in Firefox → **Send session to booker** |
| 18:00 booking | Automatic on server — laptop can be off |
| Tunnel during exam period | Auto agent handles it (if installed) |

---

## Tunnel status (one-liner)

```bash
echo "=== Tunnel ===" && (pgrep -fl "8080:127.0.0.1:8080" || echo "OFF") && \
echo "=== Localhost ===" && (curl -sf --max-time 3 http://127.0.0.1:8080/health >/dev/null && echo "OK" || echo "FAIL") && \
echo "=== Agent ===" && launchctl list 2>/dev/null | grep autobooker || echo "not installed (macOS)"
```

---

## Is the tunnel running?

```bash
pgrep -fl "8080:127.0.0.1:8080"
```

Output shows `ssh ... -L` → **on**. No output → **off**.

```bash
lsof -i :8080
```

---

## Health checks

**Via tunnel (localhost):**

```bash
curl -s http://127.0.0.1:8080/health | python3 -m json.tool | head -20
```

**Direct to server (no tunnel):**

```bash
curl -s http://YOUR_SERVER_IP:8080/health | head -c 100
```

---

## Manual tunnel

**macOS / Linux:**

```bash
cd YOUR_REPO
./scripts/tunnel.sh
```

Keep the terminal open.

**Windows (PowerShell):**

```powershell
cd YOUR_REPO
.\scripts\tunnel.ps1
```

---

## Auto tunnel

**Install (once):**

```bash
# macOS
./scripts/install-tunnel-agent.sh

# Windows (PowerShell)
.\scripts\install-tunnel-task.ps1
```

**Re-run after editing `config/local.env`:**

```bash
./scripts/install-tunnel-agent.sh   # macOS
.\scripts\install-tunnel-task.ps1   # Windows
```

**Force auto agent to run now (macOS):**

```bash
launchctl kickstart -k "gui/$(id -u)/com.kuleuven.autobooker-tunnel"
```

**Auto agent logs (macOS):**

```bash
cat ~/Library/Logs/ku-leuven-autobooker/tunnel.log
cat ~/Library/Logs/ku-leuven-autobooker/tunnel.err
```

Clear old errors:

```bash
> ~/Library/Logs/ku-leuven-autobooker/tunnel.err
```

**Run auto script manually (macOS):**

```bash
bash ~/Library/Application\ Support/ku-leuven-autobooker/run-tunnel.sh
echo "exit: $?"
```

---

## After `pkill` (tunnel killed)

Auto agent restarts within ~30 min during booking window. To fix now:

```bash
launchctl kickstart -k "gui/$(id -u)/com.kuleuven.autobooker-tunnel"
sleep 2
pgrep -fl "8080:127.0.0.1:8080" || ./scripts/tunnel.sh
```

---

## Stop tunnel

```bash
pkill -f "8080:127.0.0.1:8080"
```

---

## Booking window (is auto tunnel allowed today?)

```bash
curl -s http://YOUR_SERVER_IP:8080/health | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('booking_active_today:', d.get('booking_active_today'))
print('status:', d.get('booking_status_message'))
"
```

`booking_active_today: False` → auto agent won't start tunnel (manual tunnel still works if you need cookies).

---

## Firefox extension

1. `about:debugging` → **This Firefox** → **Load Temporary Add-on** → `extension/manifest.json`
2. Permissions: `about:addons` → extension → **Permissions** → enable listed hosts
3. After config change: **Remove** add-on → **Load** again

**Inspect console:** `about:debugging` → extension → **Inspect**

Success:

```
[Autobooker] ✓ Sent via http://127.0.0.1:8080/update-cookie
```

---

## Server (SSH)

```bash
ssh -i YOUR_SSH_KEY root@YOUR_SERVER_IP
cd /opt/ku-leuven-autobooker/server
```

**Logs:**

```bash
docker compose logs -f --tail=30
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

---

## Common errors

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `timed out (8s)` to server IP in Firefox | Campus blocks browser → external IP | Use tunnel / localhost |
| `HTTP 401` on localhost | `SECRET_KEY` mismatch | Sync `.env`, `relay-core.local.js`, `docker compose up -d --force-recreate` |
| `Address already in use` port 8080 | Tunnel already running | `pgrep -fl 8080` — don't start a second one |
| `Operation not permitted` in `tunnel.err` (old) | Stale log from before agent fix | Clear `tunnel.err`, re-run `install-tunnel-agent.sh` |
| `Not needed today` in tunnel.log | Outside booking window | Normal — use manual tunnel if you need cookies |

---

## Secret files (never commit)

- `config/local.env`
- `extension/relay-core.local.js`
- `extension/manifest.json`
- `server/.env` (on droplet)

First-time setup: `./scripts/setup-local.sh`
