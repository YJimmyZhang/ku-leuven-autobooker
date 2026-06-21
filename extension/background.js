// Background: auto-relay + message handler for kurt3 page button

const RELAY_ORIGINS = [
  "http://127.0.0.1/*",
  "http://localhost/*",
  `http://${AUTOBOOKER.SERVER_IP}/*`,
];

async function ensureHostPermissions() {
  if (!browser.permissions?.contains) return true;
  try {
    const ok = await browser.permissions.contains({ origins: RELAY_ORIGINS });
    if (ok) return true;
    const granted = await browser.permissions.request({ origins: RELAY_ORIGINS });
    if (!granted) {
      console.error("[Autobooker] Host permissions denied — enable in about:addons → Permissions");
      await notifyRelayResult({
        ok: false,
        error: "Allow localhost + server access when Firefox asks, or enable in about:addons → Permissions.",
      });
    }
    return granted;
  } catch (err) {
    console.warn("[Autobooker] permissions check:", err);
    return true;
  }
}

const KURT3_URL = AUTOBOOKER.KURT3_URL;
const KULEUVEN_DOMAIN_SUFFIX = "kuleuven.be";
const DEBOUNCE_MS = 2000;
let debounceTimer = null;
let lastSentFingerprint = null;

function isShibsessionCookie(cookie) {
  return cookie?.name?.startsWith("_shibsession");
}

function isKuleuvenCookie(cookie) {
  if (!cookie?.domain) return false;
  return (
    cookie.domain === KULEUVEN_DOMAIN_SUFFIX ||
    cookie.domain.endsWith(`.${KULEUVEN_DOMAIN_SUFFIX}`)
  );
}

function cookieFingerprint(cookies) {
  const shib = cookies.find(isShibsessionCookie);
  return shib ? `${shib.name}=${shib.value}:${cookies.length}` : null;
}

async function relayCookies(force = false) {
  let cookies;
  try {
    cookies = await getKurt3Cookies();
  } catch (err) {
    return { ok: false, error: err.message };
  }

  console.log(`[Autobooker] relayCookies: ${cookies.length} cookies`);

  const fingerprint = cookieFingerprint(cookies);
  if (!fingerprint) {
    return {
      ok: false,
      error: "No session in Firefox — log in to kurt3 in THIS browser (not Chrome/Safari).",
    };
  }

  if (!force && fingerprint === lastSentFingerprint) {
    return { ok: true, skipped: true, cookieCount: cookies.length };
  }

  if (!(await ensureHostPermissions())) {
    return { ok: false, error: "Host permissions not granted." };
  }

  const result = await autobookerRelay();
  if (result.ok) {
    lastSentFingerprint = fingerprint;
    console.log("[Autobooker] ✓ Relayed cookies.");
  } else {
    console.error("[Autobooker] Relay failed:", result.error);
  }
  return result;
}

function scheduleRelay(force = false) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    relayCookies(force).catch((err) => console.error("[Autobooker]", err));
  }, DEBOUNCE_MS);
}

browser.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.action === "relay") {
    relayCookies(true).then(sendResponse);
    return true;
  }
});

browser.cookies.onChanged.addListener((changeInfo) => {
  const { cookie, removed } = changeInfo;
  if (removed || !isKuleuvenCookie(cookie) || !isShibsessionCookie(cookie)) return;
  scheduleRelay(true);
});

browser.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" || !tab.url?.startsWith(KURT3_URL)) return;
  console.log("[Autobooker] kurt3 loaded — auto-relaying");
  scheduleRelay(true);
});

browser.alarms.create("rescan-cookies", { periodInMinutes: 30 });
browser.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "rescan-cookies") {
    relayCookies(true).catch((err) => console.error("[Autobooker]", err));
  }
});

browser.action.onClicked.addListener(async () => {
  if (!(await ensureHostPermissions())) return;
  const result = await relayCookies(true);
  await notifyRelayResult(result);
});

ensureHostPermissions()
  .then(() => relayCookies(true))
  .catch((err) => console.error("[Autobooker] startup:", err));
