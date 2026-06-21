// Floating button on kurt3 — click to send cookies (shows success/error on page)

(function () {
  if (document.getElementById("autobooker-btn")) return;

  const btn = document.createElement("button");
  btn.id = "autobooker-btn";
  btn.textContent = "Send session to booker";
  btn.style.cssText = [
    "position:fixed",
    "bottom:20px",
    "right:20px",
    "z-index:2147483647",
    "padding:12px 16px",
    "background:#1a73e8",
    "color:#fff",
    "border:none",
    "border-radius:8px",
    "cursor:pointer",
    "font:14px system-ui,sans-serif",
    "box-shadow:0 2px 12px rgba(0,0,0,.35)",
  ].join(";");

  btn.addEventListener("click", () => {
    btn.textContent = "Sending…";
    btn.disabled = true;
    btn.style.background = "#666";

    browser.runtime.sendMessage({ action: "relay" }, (response) => {
      btn.disabled = false;
      if (browser.runtime.lastError) {
        btn.textContent = "Extension error — reload add-on";
        btn.style.background = "#b42318";
        console.error("[Autobooker]", browser.runtime.lastError.message);
        return;
      }
      if (response?.ok) {
        btn.textContent = `Sent ${response.cookieCount} cookies`;
        btn.style.background = "#067d3e";
      } else {
        const msg = response?.error || "Failed — see extension console";
        btn.textContent = msg.length > 40 ? msg.slice(0, 40) + "…" : msg;
        btn.style.background = "#b42318";
        console.error("[Autobooker]", response);
      }
    });
  });

  document.body.appendChild(btn);
})();
