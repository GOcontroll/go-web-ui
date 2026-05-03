// CAN page: build a card per bus, poll busload every second, draw a 30s sparkline.

const HISTORY_LEN = 30;            // seconds of busload history shown
const POLL_INTERVAL_MS = 1000;     // sample cadence
const BITRATE_OPTIONS = [125000, 250000, 500000, 1000000];

const history = {};   // { canX: number[HISTORY_LEN] }

function fmtBitrate(bps) {
  if (!bps) return "—";
  if (bps >= 1000000) return (bps % 1000000 ? (bps / 1e6).toFixed(2) : (bps / 1e6).toFixed(0)) + " Mbit/s";
  if (bps >= 1000) return (bps % 1000 ? (bps / 1000).toFixed(1) : (bps / 1000).toFixed(0)) + " kbit/s";
  return bps + " bit/s";
}

function badge(state, up) {
  // map go-can state ("up", "stopped", "error-active", "absent") + up flag → badge color
  if (state === "absent" || !state) return { cls: "gray", text: "ABSENT" };
  if (!up || state === "stopped") return { cls: "red", text: "DOWN" };
  if (state.startsWith("error")) return { cls: "yellow", text: state.toUpperCase() };
  return { cls: "green", text: "UP" };
}

function renderCard(iface) {
  const opts = BITRATE_OPTIONS.map(b =>
    `<option value="${b}">${fmtBitrate(b)}</option>`
  ).join("");
  const card = document.createElement("section");
  card.className = "card can-card";
  card.dataset.iface = iface.name;
  card.innerHTML = `
    <div class="can-card-head">
      <span class="name">${iface.name.toUpperCase()}</span>
      <span class="badge" data-role="state">…</span>
    </div>
    <div class="bitrate-row">
      <div class="form-group">
        <label>Bitrate</label>
        <select data-role="bitrate-select">${opts}</select>
      </div>
      <button class="btn primary" type="button" data-role="apply">Apply</button>
    </div>
    <p class="alert-box" data-role="status"></p>
    <div class="busload-row">
      <svg class="busload-chart" viewBox="0 0 30 100" preserveAspectRatio="none" aria-label="busload over last 30 seconds">
        <polygon class="busload-fill" data-role="fill" points="" />
        <polyline class="busload-line" data-role="line" points="" />
      </svg>
      <span class="busload-value" data-role="load">—</span>
    </div>
    <div class="busload-axis"><span>30s ago</span><span>now</span></div>
  `;
  return card;
}

function applyIfaceState(card, iface) {
  const select = card.querySelector('[data-role="bitrate-select"]');
  // ensure current bitrate is selectable, even if it's not in our preset list
  if (iface.bitrate && !BITRATE_OPTIONS.includes(iface.bitrate)) {
    const opt = document.createElement("option");
    opt.value = iface.bitrate;
    opt.textContent = fmtBitrate(iface.bitrate) + " (custom)";
    select.appendChild(opt);
  }
  if (iface.bitrate) select.value = iface.bitrate;

  const b = badge(iface.state, iface.up);
  const stateEl = card.querySelector('[data-role="state"]');
  stateEl.className = "badge " + b.cls;
  stateEl.textContent = b.text;

  card.classList.toggle("absent", !iface.present);
}

function wireApply(card) {
  const btn = card.querySelector('[data-role="apply"]');
  const select = card.querySelector('[data-role="bitrate-select"]');
  const status = card.querySelector('[data-role="status"]');
  const name = card.dataset.iface;
  btn.addEventListener("click", async () => {
    const bitrate = parseInt(select.value, 10);
    btn.disabled = true;
    status.classList.remove("ok", "info", "fail");
    status.textContent = "";
    try {
      const resp = await post_json("/api/set_can_bitrate", { name, bitrate });
      if (resp.err) {
        status.textContent = resp.err;
        alert_class_switch(status, "fail");
      } else {
        status.textContent = `Bitrate set to ${fmtBitrate(bitrate)}`;
        alert_class_switch(status, "ok");
      }
    } catch (err) {
      status.textContent = "Request failed: " + err;
      alert_class_switch(status, "fail");
    } finally {
      btn.disabled = false;
    }
  });
}

function pushSample(name, value) {
  if (!history[name]) history[name] = new Array(HISTORY_LEN).fill(0);
  history[name].push(value);
  history[name].shift();
}

function paintChart(card, name) {
  const h = history[name];
  if (!h) return;
  const linePoints = h.map((v, i) => {
    const y = 100 - Math.max(0, Math.min(100, v));
    return `${i},${y.toFixed(2)}`;
  }).join(" ");
  // Polygon for fill: line + bottom-right + bottom-left to close
  const fillPoints = `0,100 ${linePoints} ${HISTORY_LEN - 1},100`;
  card.querySelector('[data-role="line"]').setAttribute("points", linePoints);
  card.querySelector('[data-role="fill"]').setAttribute("points", fillPoints);
  const cur = h[h.length - 1];
  card.querySelector('[data-role="load"]').textContent = cur.toFixed(1) + "%";
}

async function pollLoads() {
  try {
    const res = await (await fetch("/api/get_can_load")).json();
    if (res.err) {
      console.log("get_can_load:", res.err);
      return;
    }
    const cards = document.querySelectorAll(".can-card");
    cards.forEach(card => {
      const name = card.dataset.iface;
      if (typeof res[name] === "number") {
        pushSample(name, res[name]);
        paintChart(card, name);
      }
    });
  } catch (err) {
    console.log("poll error:", err);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const grid = document.getElementById("can-grid");
  const baseLabel = document.getElementById("baseboard-label");
  try {
    const res = await (await fetch("/api/get_can_list")).json();
    if (res.err) {
      grid.innerHTML = `<p class="alert-box fail">${res.err}</p>`;
      return;
    }
    if (baseLabel && res.baseboard) {
      baseLabel.textContent = res.baseboard;
    }
    grid.textContent = "";
    res.interfaces.forEach(iface => {
      const card = renderCard(iface);
      grid.appendChild(card);
      applyIfaceState(card, iface);
      wireApply(card);
    });
    // Kick off polling
    pollLoads();
    setInterval(pollLoads, POLL_INTERVAL_MS);
  } catch (err) {
    grid.innerHTML = `<p class="alert-box fail">Could not load CAN information: ${err}</p>`;
  }
}, false);
