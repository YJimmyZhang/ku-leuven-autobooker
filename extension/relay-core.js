// Shared cookie relay logic (safe to commit — no secrets here).
//
// Real SECRET_KEY and server URL: extension/relay-core.local.js (gitignored).
// Copy extension/relay-core.local.js.example → relay-core.local.js on first setup.
//
// KU Leuven campus WiFi blocks many external hosts. On campus, run scripts/tunnel.sh
// then send cookies via localhost. Off campus, relay-core.local.js can include your
// server IP in WEBHOOK_URLS.

const AUTOBOOKER_DEFAULTS = {
  SECRET_KEY: "CHANGE_ME",
  KURT3_URL: "https://kurt3.ghum.kuleuven.be/",
  WEBHOOK_URLS: [
    "http://127.0.0.1:8080/update-cookie",
    "http://localhost:8080/update-cookie",
  ],
  SERVER_IP: "YOUR_SERVER_IP",
  SSH_KEY: "~/.ssh/id_ed25519_do",
};

const AUTOBOOKER = {
  ...AUTOBOOKER_DEFAULTS,
  ...(typeof AUTOBOOKER_LOCAL !== "undefined" ? AUTOBOOKER_LOCAL : {}),
};

function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`${label} (${ms / 1000}s)`)), ms)
    ),
  ]);
}

async function getKurt3Cookies() {
  try {
    const byUrl = await withTimeout(
      browser.cookies.getAll({ url: AUTOBOOKER.KURT3_URL }),
      8000,
      "Cookie read timed out"
    );
    if (byUrl.length > 0) return byUrl;
  } catch (err) {
    console.warn("[Autobooker] getAll by url failed:", err);
  }

  const byDomain = await withTimeout(
    browser.cookies.getAll({ domain: "kuleuven.be" }),
    8000,
    "Cookie read timed out"
  );
  return byDomain.filter((c) => c.domain?.includes("kuleuven.be"));
}

async function postToWebhook(url, payload) {
  const response = await withTimeout(
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
    8000,
    "Server request timed out"
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 120)}`);
  }
  return url;
}

async function autobookerRelay() {
  if (AUTOBOOKER.SECRET_KEY === "CHANGE_ME") {
    return {
      ok: false,
      error: "Set SECRET_KEY in extension/relay-core.local.js (run scripts/setup-local.sh).",
    };
  }

  let cookies;
  try {
    cookies = await getKurt3Cookies();
  } catch (err) {
    return { ok: false, error: err.message };
  }

  console.log(`[Autobooker] Found ${cookies.length} cookies`);

  const shib = cookies.find((c) => c.name.startsWith("_shibsession"));
  if (!shib) {
    return {
      ok: false,
      error: "Not logged in — open kurt3 in Firefox and sign in first.",
    };
  }

  const payload = {
    secret: AUTOBOOKER.SECRET_KEY,
    cookie_name: shib.name,
    cookie_value: shib.value,
    domain: shib.domain,
    cookies: cookies.map((c) => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
    })),
    captured_at: new Date().toISOString(),
  };

  const errors = [];
  for (const url of AUTOBOOKER.WEBHOOK_URLS) {
    try {
      await postToWebhook(url, payload);
      console.log(`[Autobooker] ✓ Sent via ${url}`);
      return { ok: true, cookieCount: cookies.length, via: url };
    } catch (err) {
      console.warn(`[Autobooker] Failed ${url}:`, err.message);
      errors.push(`${url}: ${err.message}`);
    }
  }

  const ip = AUTOBOOKER.SERVER_IP;
  return {
    ok: false,
    error: `Could not reach server. On KU WiFi run: ssh -i ${AUTOBOOKER.SSH_KEY} -N -L 8080:127.0.0.1:8080 root@${ip}`,
    details: errors,
  };
}

async function notifyRelayResult(result) {
  const title = result.ok ? "Cookies sent ✓" : "Cookie relay failed";
  const message = result.ok
    ? `${result.cookieCount} cookies → server`
    : result.error;

  try {
    await browser.notifications.create({
      type: "basic",
      iconUrl: "icon.svg",
      title,
      message,
    });
  } catch {
    console.log("[Autobooker]", title, "—", message);
  }
}
