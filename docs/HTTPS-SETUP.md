# Tunnel-free setup: HTTPS via a free subdomain + Caddy

This makes the Firefox extension send cookies over `https://` directly to your
server from **any network** — no SSH tunnel, no terminal kept open, and your KU
Leuven session cookies are encrypted in transit.

> **Placeholders:** replace `YOUR_DROPLET_IP` with your server's public IP and
> `YOUR_SUBDOMAIN.duckdns.org` with the hostname you create in step 1. Your real
> values live only in gitignored files (`server/.env`, `extension/*.local.js`,
> `extension/manifest.json`) — keep them out of anything you commit.

Why this is needed: the extension runs in a secure (`moz-extension://`) context.
Firefox lets a secure context talk to `localhost` over plain http (that's why the
tunnel works) but blocks plain http to a public IP as *mixed content*. Serving the
server over real HTTPS removes that block and the cleartext-credentials risk in one
move. HTTPS on port 443 is also the one path campus WiFi can't selectively block.

There are three one-time steps. Two you do (DuckDNS + server), one is already done
in the repo (the config below).

---

## 1. Get a free subdomain (DuckDNS) — 2 minutes

1. Go to https://www.duckdns.org and sign in (GitHub/Google — no payment, no card).
2. Pick a subdomain. You get `YOUR_SUBDOMAIN.duckdns.org`.
3. In the **current ip** box for that subdomain, enter your server's IP
   `YOUR_DROPLET_IP` and click **update ip**. (DuckDNS pre-fills the IP you're
   browsing from — make sure you overwrite it with the server's IP, not your
   laptop/campus IP.)
4. Confirm it resolves (from your Mac):

   ```bash
   dig +short YOUR_SUBDOMAIN.duckdns.org
   # should print YOUR_DROPLET_IP
   ```

DNS may take a couple of minutes the first time.

---

## 2. Deploy on the server — 5 minutes

SSH in and update the code + env:

```bash
ssh -i ~/.ssh/id_ed25519_do root@YOUR_DROPLET_IP

cd /opt/ku-leuven-autobooker
git pull            # or rsync the updated server/ folder up, as before

cd server
nano .env
```

In `.env`, set your real hostname (and keep SECRET_KEY as-is):

```
DOMAIN=YOUR_SUBDOMAIN.duckdns.org
```

Then re-run the deploy (it now opens 80/443, closes public 8080, and starts Caddy):

```bash
bash deploy/setup-droplet.sh
# or, if Docker is already installed:
docker compose up -d --build
```

Caddy fetches a Let's Encrypt certificate on the first request — give it ~30s,
then verify from your Mac:

```bash
curl https://YOUR_SUBDOMAIN.duckdns.org/health
# expect a 200 / health JSON, served over real HTTPS
```

If `curl` shows a cert error, wait a minute (cert still issuing) and retry. Make
sure ports 80 and 443 are reachable — Let's Encrypt validates over port 80.

---

## 3. Point the extension at HTTPS — 1 minute

Edit `extension/relay-core.local.js` and put your real domain first in the list:

```js
WEBHOOK_URLS: [
  "https://YOUR_SUBDOMAIN.duckdns.org/update-cookie",
  "http://127.0.0.1:8080/update-cookie",   // tunnel fallback, fine to keep
  "http://localhost:8080/update-cookie",
],
```

Edit `extension/manifest.json` and set the matching host permission:

```json
"https://YOUR_SUBDOMAIN.duckdns.org/*"
```

Then in Firefox: `about:debugging` → **This Firefox** → **Reload** the extension
(or remove/re-add the temporary add-on). Reloading is required because
`host_permissions` changed.

---

## 4. Verify

1. Open kurt3 in Firefox and sign in.
2. Click the extension button.
3. Open the Browser Console (Cmd+Shift+J) and look for:

   ```
   [Autobooker] ✓ Sent via https://YOUR_SUBDOMAIN.duckdns.org/update-cookie
   ```

That `✓ Sent via https://…` line means it went directly over HTTPS — no tunnel
involved. You can now stop the tunnel / uninstall the auto-tunnel agent if you want:

```bash
launchctl bootout gui/$(id -u)/com.kuleuven.autobooker.tunnel 2>/dev/null || true
```

The localhost entries staying in `WEBHOOK_URLS` are harmless — they're only tried
if the HTTPS endpoint is ever unreachable.

---

## Notes

- The **18:00 booking runs on the server** regardless — none of this affects it.
- Renewals are automatic; Caddy handles cert renewal in the background.
- If you ever change the server's IP, update the DuckDNS record to match.
- Security: cookies now travel encrypted end-to-end. The server no longer exposes
  port 8080 publicly (it binds to `127.0.0.1` and is reached only via Caddy or the
  tunnel).

### Hosting cost

You need an **always-on, internet-reachable server** because the booking fires at
18:00 server-side — it can't depend on your laptop being awake. Any VPS works
(DigitalOcean, Hetzner, Linode, …) for a few dollars a month, or a home server /
Raspberry Pi you already leave on (with port forwarding) for free. Caddy + DuckDNS
add **no cost** on top. Note that Fly.io and Railway no longer offer a usable free
tier for an always-on service.
