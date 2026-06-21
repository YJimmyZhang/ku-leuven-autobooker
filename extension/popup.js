const statusEl = document.getElementById("status");

function setStatus(text, ok) {
  statusEl.textContent = text;
  statusEl.className = ok === true ? "ok" : ok === false ? "err" : "";
}

document.getElementById("relay").addEventListener("click", async () => {
  setStatus("Sending…");

  try {
    const response = await autobookerRelay();
    if (response.ok) {
      setStatus(`✓ Sent ${response.cookieCount} cookies to server.`, true);
    } else {
      setStatus(response.error || "Failed.", false);
    }
  } catch (err) {
    setStatus(String(err), false);
  }
});
