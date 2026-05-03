// Wi-Fi page: pick AP mode or client (connect-to-network) mode.
// Backend endpoints used:
//   GET  /api/get_wifi              → {state: bool}
//   POST /api/set_wifi              → {new_state}
//   GET  /api/get_wifi_type         → {type: "ap"|"wifi"}
//   POST /api/set_wifi_type         → {new_type}
//   GET  /api/get_ap_info           → {ssid}
//   POST /api/set_ap_ssid           → req.json = "<new ssid>"
//   POST /api/set_ap_pass           → req.json = "<new password>"
//   GET  /api/get_wifi_networks     → {<ssid>: {connected, mac, ssid, strength, security}, ...}
//   POST /api/connect_to_wifi_network → {ssid, password}

let currentMode = null;        // "ap" | "wifi" | null
let scanInFlight = false;
let activeRefreshTimer = null;
let lastActive = null;         // last fetched /api/get_active_wifi payload

// ---------------------------------------------------------------------------
// Confirmation helpers (built on showModal in common.js)
// ---------------------------------------------------------------------------

function confirmWifiChange(actionDescription, primaryLabel) {
  return new Promise(resolve => {
    let resolved = false;
    const safe = v => { if (!resolved) { resolved = true; resolve(v); } };
    const overlay = showModal({
      title: "This may disconnect you",
      variant: "warn",
      body: `<p>You are about to <strong>${actionDescription}</strong>.</p>
             <p>If you are currently connected to this controller via Wi-Fi, your connection will most likely drop.
                Make sure you have an alternative way to reach the controller (Ethernet, USB, …) before continuing.</p>`,
      actions: [
        { label: "Cancel",         onClick: () => safe(false) },
        { label: primaryLabel || "Continue", primary: true, onClick: () => safe(true) },
      ],
    });
    // Resolve(false) on overlay click / Esc dismissal.
    const obs = new MutationObserver(() => {
      if (!overlay.parentNode) { obs.disconnect(); safe(false); }
    });
    obs.observe(document.body, { childList: true });
  });
}

function promptWifiPassword(ssid, isOpen) {
  return new Promise(resolve => {
    let resolved = false;
    const safe = v => { if (!resolved) { resolved = true; resolve(v); } };
    const passField = isOpen
      ? ""
      : `<div class="form-group" style="margin-top:14px;">
           <label for="modal-pass">Password</label>
           <input id="modal-pass" type="password" autocomplete="off">
         </div>`;
    const overlay = showModal({
      title: `Connect to ${escapeHtml(ssid)}`,
      variant: "warn",
      body: `<p>Switching to a different Wi-Fi network will disconnect you from this controller if you reached it via Wi-Fi.
               Make sure you have another way to reach it.</p>
             ${passField}`,
      actions: [
        { label: "Cancel",  onClick: () => safe(null) },
        { label: "Connect", primary: true, onClick: () => {
          if (isOpen) { safe(""); return; }
          const v = overlay.querySelector("#modal-pass")?.value ?? "";
          safe(v);
        }},
      ],
    });
    // Focus the password input (showModal focuses the primary button by default).
    setTimeout(() => overlay.querySelector("#modal-pass")?.focus(), 0);
    const obs = new MutationObserver(() => {
      if (!overlay.parentNode) { obs.disconnect(); safe(null); }
    });
    obs.observe(document.body, { childList: true });
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}

// ---------------------------------------------------------------------------
// Signal-bars SVG (4 bars, fill count based on 0..100 strength)
// ---------------------------------------------------------------------------
function signalBarsSvg(strength) {
  const s = parseInt(strength, 10) || 0;
  const filled = s >= 76 ? 4 : s >= 51 ? 3 : s >= 26 ? 2 : s > 0 ? 1 : 0;
  const bars = [
    {x: 0,  h: 4 },
    {x: 5,  h: 7 },
    {x: 10, h: 10},
    {x: 15, h: 14},
  ];
  return `<svg class="signal-bars" viewBox="0 0 19 14" aria-label="signal ${s}%">
    ${bars.map((b, i) =>
      `<rect class="${i < filled ? 'on' : ''}" x="${b.x}" y="${14 - b.h}" width="3" height="${b.h}" rx="1" />`
    ).join("")}
  </svg>`;
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

function setMode(mode) {
  // Toggle visibility of mode-specific cards
  const inClient = (mode === "wifi");
  document.getElementById("ap-card").style.display     = (mode === "ap") ? "" : "none";
  document.getElementById("client-card").style.display = inClient ? "" : "none";
  // active/saved cards default to hidden; their loaders unhide them when relevant
  if (!inClient) {
    document.getElementById("active-card").style.display = "none";
    document.getElementById("saved-card").style.display  = "none";
    stopActiveRefresh();
  }
  // Sync radios
  document.querySelector(`input[name="wifi-mode"][value="${mode}"]`).checked = true;
  currentMode = mode;
  if (inClient) {
    loadActiveWifi();
    loadSavedNetworks();
    startActiveRefresh();
  }
}

async function applyWifiMode(targetMode) {
  if (targetMode === currentMode) return;
  const desc = targetMode === "ap"
    ? "switch the controller into Access Point mode"
    : "stop the Access Point and connect to an existing network";
  const ok = await confirmWifiChange(desc, "Switch mode");
  if (!ok) {
    // Revert radio to the actual current mode
    setMode(currentMode);
    return;
  }
  try {
    const resp = await post_json("/api/set_wifi_type", { new_type: targetMode });
    if (resp.err) {
      showModal({ title: "Could not switch mode", variant: "danger", body: `<p>${escapeHtml(resp.err)}</p>` });
      setMode(currentMode);
      return;
    }
    setMode(targetMode);
    if (targetMode === "ap") loadApInfo();
  } catch (err) {
    showModal({ title: "Could not switch mode", variant: "danger", body: `<p>${escapeHtml(String(err))}</p>` });
    setMode(currentMode);
  }
}

// ---- AP card ----

async function loadApInfo() {
  const ssidIn = document.getElementById("ap_ssid_current");
  try {
    const resp = await (await fetch("/api/get_ap_info")).json();
    if (resp.err) {
      ssidIn.value = "";
      ssidIn.placeholder = "(could not read AP profile)";
      return;
    }
    ssidIn.value = resp.ssid || "";
  } catch (err) {
    ssidIn.value = "";
  }
}

async function set_ap_ssid() {
  const input  = document.getElementById("ap_ssid_current");
  const result = document.getElementById("set_ap_ssid_result");
  const ssid   = input.value.trim();
  if (!ssid) {
    alert_class_switch(result, "info");
    result.innerText = "SSID cannot be empty";
    return;
  }
  const ok = await confirmWifiChange(`change the access-point SSID to "${ssid}"`, "Change SSID");
  if (!ok) return;
  try {
    const resp = await post_json("/api/set_ap_ssid", ssid);
    if (resp.err) {
      result.innerText = "Error: " + resp.err;
      alert_class_switch(result, "fail");
    } else {
      result.innerText = "Success — clients reconnect with the new SSID.";
      alert_class_switch(result, "ok");
    }
  } catch (err) {
    result.innerText = "Could not set SSID: " + err;
    alert_class_switch(result, "fail");
  }
}

async function set_ap_pass() {
  const input  = document.getElementById("ap_pass");
  const result = document.getElementById("set_ap_pass_result");
  const pass   = input.value;
  if (pass.length < 8) {
    alert_class_switch(result, "info");
    result.innerText = "Password must be at least 8 characters";
    return;
  }
  const ok = await confirmWifiChange("change the access-point password", "Change password");
  if (!ok) return;
  try {
    const resp = await post_json("/api/set_ap_pass", pass);
    if (resp.err) {
      result.innerText = "Error: " + resp.err;
      alert_class_switch(result, "fail");
    } else {
      result.innerText = "Success — clients reconnect with the new password.";
      alert_class_switch(result, "ok");
      input.value = "";
    }
  } catch (err) {
    result.innerText = "Could not set password: " + err;
    alert_class_switch(result, "fail");
  }
}

function toggle_ap_pass() {
  const input = document.getElementById("ap_pass");
  input.type = input.type === "password" ? "text" : "password";
}

// ---- Active connection card ----

async function loadActiveWifi() {
  try {
    const resp = await (await fetch("/api/get_active_wifi")).json();
    if (resp.err || !resp.connected) {
      document.getElementById("active-card").style.display = "none";
      lastActive = null;
      return;
    }
    lastActive = resp;
    renderActive(resp);
    document.getElementById("active-card").style.display = "";
  } catch (err) {
    console.log("get_active_wifi:", err);
  }
}

function renderActive(a) {
  document.getElementById("active-bars").innerHTML = signalBarsSvg(a.signal || 0);
  document.getElementById("active-ssid").textContent = a.ssid || a.name || "—";
  const metaParts = [];
  if (a.ip) metaParts.push(a.ip);
  if (a.signal) metaParts.push(`${a.signal}%`);
  if (a.security) metaParts.push(a.security);
  document.getElementById("active-meta").textContent = metaParts.join(" · ") || "Connected";

  document.getElementById("active-detail-ssid").textContent     = a.ssid || a.name || "—";
  document.getElementById("active-detail-ip").textContent       = a.ip || "—";
  document.getElementById("active-detail-bssid").textContent    = a.bssid || "—";
  document.getElementById("active-detail-signal").textContent   = a.signal ? a.signal + " %" : "—";
  document.getElementById("active-detail-security").textContent = a.security || "—";
  document.getElementById("active-detail-freq").textContent     = a.frequency || "—";
  document.getElementById("active-detail-rate").textContent     = a.rate || "—";
}

function toggleActiveDetails() {
  const summary = document.getElementById("active-summary");
  const expanded = summary.getAttribute("aria-expanded") === "true";
  summary.setAttribute("aria-expanded", expanded ? "false" : "true");
}

async function forgetActive() {
  if (!lastActive || !lastActive.name) return;
  const ok = await confirmWifiChange(
    `forget the saved network "${lastActive.name}" and disconnect from it`,
    "Forget");
  if (!ok) return;
  try {
    const resp = await post_json("/api/forget_wifi_network", { name: lastActive.name });
    if (resp.err) {
      showModal({ title: "Could not forget network", variant: "danger", body: `<p>${escapeHtml(resp.err)}</p>` });
      return;
    }
    document.getElementById("active-card").style.display = "none";
    lastActive = null;
    loadSavedNetworks();
  } catch (err) {
    showModal({ title: "Could not forget network", variant: "danger", body: `<p>${escapeHtml(String(err))}</p>` });
  }
}

function startActiveRefresh() {
  stopActiveRefresh();
  activeRefreshTimer = setInterval(loadActiveWifi, 5000);
}
function stopActiveRefresh() {
  if (activeRefreshTimer) { clearInterval(activeRefreshTimer); activeRefreshTimer = null; }
}

// ---- Saved networks card ----

async function loadSavedNetworks() {
  const card = document.getElementById("saved-card");
  const list = document.getElementById("saved-list");
  try {
    const resp = await (await fetch("/api/get_saved_wifi_networks")).json();
    if (resp.err) {
      card.style.display = "none";
      console.log("get_saved_wifi_networks:", resp.err);
      return;
    }
    // Hide currently active one — it is already shown in the Connected card
    const inactive = resp.filter(n => !n.active);
    if (inactive.length === 0) {
      card.style.display = "none";
      return;
    }
    list.innerHTML = "";
    inactive.forEach(n => list.appendChild(renderSavedRow(n)));
    card.style.display = "";
  } catch (err) {
    card.style.display = "none";
    console.log(err);
  }
}

function renderSavedRow(n) {
  const row = document.createElement("div");
  row.className = "saved-row";
  row.innerHTML = `
    <div class="net-info">
      <div class="net-ssid">${escapeHtml(n.ssid || n.name)}</div>
      <div class="net-meta">saved${n.autoconnect ? " · auto-connect" : ""}</div>
    </div>
    <div class="net-actions">
      <button class="btn sm" type="button" data-act="connect">Connect</button>
      <button class="btn danger sm" type="button" data-act="forget">Forget</button>
    </div>
  `;
  row.querySelector('[data-act="connect"]').addEventListener("click", () => connectSaved(n.name, n.ssid));
  row.querySelector('[data-act="forget"]').addEventListener("click", () => forgetSaved(n.name, n.ssid));
  return row;
}

async function connectSaved(name, ssid) {
  const ok = await confirmWifiChange(
    `connect to the saved network "${ssid || name}"`,
    "Connect");
  if (!ok) return;
  const connOverlay = showModal({
    title: `Connecting to ${escapeHtml(ssid || name)}…`,
    variant: "info",
    body: `<p>Activating saved profile. This page may stop responding if the controller switches IP.</p>`,
    actions: [],
  });
  try {
    const resp = await post_json("/api/connect_saved_wifi", { name });
    closeModal(connOverlay);
    if (resp.err) {
      showModal({ title: "Could not connect", variant: "danger", body: `<p>${escapeHtml(resp.err)}</p>` });
      return;
    }
    loadActiveWifi();
    loadSavedNetworks();
  } catch (err) {
    closeModal(connOverlay);
    showModal({
      title: "Lost contact with the controller",
      variant: "warn",
      body: `<p>The browser could not reach the controller. The controller has likely joined <strong>${escapeHtml(ssid || name)}</strong>.
              Find its new IP and reload.</p>`,
    });
  }
}

async function forgetSaved(name, ssid) {
  const ok = await confirmWifiChange(
    `forget the saved network "${ssid || name}"`,
    "Forget");
  if (!ok) return;
  try {
    const resp = await post_json("/api/forget_wifi_network", { name });
    if (resp.err) {
      showModal({ title: "Could not forget network", variant: "danger", body: `<p>${escapeHtml(resp.err)}</p>` });
      return;
    }
    loadSavedNetworks();
  } catch (err) {
    showModal({ title: "Could not forget network", variant: "danger", body: `<p>${escapeHtml(String(err))}</p>` });
  }
}

// ---- Client card (scan + connect) ----

async function scanNetworks() {
  if (scanInFlight) return;
  scanInFlight = true;
  const status = document.getElementById("scan-status");
  const button = document.getElementById("scan-btn");
  const list   = document.getElementById("network-list");
  button.disabled = true;
  status.textContent = "Scanning…";
  try {
    const resp = await (await fetch("/api/get_wifi_networks")).json();
    if (resp.err) {
      list.innerHTML = "";
      status.textContent = "";
      showModal({ title: "Scan failed", variant: "danger", body: `<p>${escapeHtml(resp.err)}</p>` });
      return;
    }
    const entries = Object.values(resp).filter(n => n.ssid && n.ssid !== "--");
    // Sort: connected first, then by strength desc
    entries.sort((a, b) => {
      if (a.connected !== b.connected) return a.connected ? -1 : 1;
      return (parseInt(b.strength, 10) || 0) - (parseInt(a.strength, 10) || 0);
    });
    list.innerHTML = "";
    if (entries.length === 0) {
      list.innerHTML = `<div class="network-row" style="justify-content:center;color:var(--muted);">No networks found.</div>`;
    } else {
      entries.forEach(n => list.appendChild(renderNetworkRow(n)));
    }
    status.textContent = `${entries.length} network${entries.length === 1 ? "" : "s"} · ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    status.textContent = "";
    showModal({ title: "Scan failed", variant: "danger", body: `<p>${escapeHtml(String(err))}</p>` });
  } finally {
    button.disabled = false;
    scanInFlight = false;
  }
}

function renderNetworkRow(n) {
  const isOpen = !n.security || n.security.trim() === "" || n.security === "--";
  const row = document.createElement("div");
  row.className = "network-row" + (n.connected ? " connected" : "");
  row.innerHTML = `
    ${signalBarsSvg(n.strength)}
    <div class="net-info">
      <div class="net-ssid">${escapeHtml(n.ssid)}${n.connected ? '  ·  connected' : ''}</div>
      <div class="net-meta">
        <span>${escapeHtml(n.security || "open")}</span>
        <span>${n.strength || 0}%</span>
      </div>
    </div>
    <div class="net-actions">
      <button class="btn ${n.connected ? '' : 'primary'} sm" type="button">${n.connected ? 'Reconnect' : 'Connect'}</button>
    </div>
  `;
  row.querySelector("button").addEventListener("click", () => connectToNetwork(n.ssid, isOpen));
  return row;
}

async function connectToNetwork(ssid, isOpen) {
  const password = await promptWifiPassword(ssid, isOpen);
  if (password === null) return;  // cancelled
  // Show a "connecting" modal — note the page will likely lose connectivity right after this.
  const connOverlay = showModal({
    title: `Connecting to ${escapeHtml(ssid)}…`,
    variant: "info",
    body: `<p>Negotiating with the network. This page may stop responding if the controller switches IP.</p>
           <p class="muted" style="font-size:12px;">If the page hangs, find the controller's new IP (DHCP lease, mDNS, or your router) and reload.</p>`,
    actions: [], // no buttons, will be replaced/dismissed below
  });
  try {
    const resp = await post_json("/api/connect_to_wifi_network", { ssid, password });
    closeModal(connOverlay);
    if (resp.err) {
      showModal({ title: "Could not connect", variant: "danger", body: `<p>${escapeHtml(resp.err)}</p>` });
      return;
    }
    showModal({
      title: "Connected",
      variant: "info",
      body: `<p>The controller is now connected to <strong>${escapeHtml(ssid)}</strong>.</p>
             <p class="muted" style="font-size:12px;">The connection is saved and will auto-restore after a reboot.</p>`,
    });
    loadActiveWifi();
    loadSavedNetworks();
    scanNetworks();
  } catch (err) {
    closeModal(connOverlay);
    // The fetch likely failed because the controller dropped the AP — that's expected.
    showModal({
      title: "Lost contact with the controller",
      variant: "warn",
      body: `<p>The browser could not reach the controller after the connect request.
                This usually means the AP went down and the controller has joined <strong>${escapeHtml(ssid)}</strong>.</p>
             <p class="muted" style="font-size:12px;">Find its new IP on your network and open the Web UI there.</p>`,
    });
  }
}

// ---- Wi-Fi radio toggle ----

async function set_wifi() {
  const cb = document.getElementById("wifi");
  const newState = cb.checked;
  if (!newState) {
    const ok = await confirmWifiChange("turn the Wi-Fi radio off entirely", "Turn off");
    if (!ok) { cb.checked = true; return; }
  }
  try {
    const resp = await post_json("/api/set_wifi", { new_state: newState });
    if (resp.err) {
      cb.checked = !newState;
      showModal({ title: "Could not change Wi-Fi state", variant: "danger", body: `<p>${escapeHtml(resp.err)}</p>` });
    }
  } catch (err) {
    cb.checked = !newState;
    showModal({ title: "Could not change Wi-Fi state", variant: "danger", body: `<p>${escapeHtml(String(err))}</p>` });
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  // Wifi radio state
  try {
    const w = await (await fetch("/api/get_wifi")).json();
    if (!w.err) document.getElementById("wifi").checked = !!w.state;
  } catch (_) {}

  // Mode
  try {
    const t = await (await fetch("/api/get_wifi_type")).json();
    if (!t.err && (t.type === "ap" || t.type === "wifi")) {
      setMode(t.type);
      if (t.type === "ap") loadApInfo();
    } else {
      setMode("ap"); // sensible default if undeterminable
      loadApInfo();
    }
  } catch (_) {
    setMode("ap");
    loadApInfo();
  }

  // Wire mode radios
  document.querySelectorAll('input[name="wifi-mode"]').forEach(radio => {
    radio.addEventListener("change", e => applyWifiMode(e.target.value));
  });
}, false);
