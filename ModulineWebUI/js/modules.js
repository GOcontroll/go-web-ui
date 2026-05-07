const CHEVRON_SVG = '<svg class="module-chevron" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5"/></svg>';

function render_module_entry(m, manifest) {
  const entry = document.createElement("div");
  entry.className = "module-entry";

  const row = document.createElement("div");
  row.className = "module-row";
  if (!m.empty && m.recognised) row.classList.add("clickable");

  const slot = document.createElement("div");
  slot.className = "module-slot";
  slot.textContent = "Slot " + m.slot;
  row.appendChild(slot);

  const meta = document.createElement("div");
  meta.className = "module-meta";

  if (m.empty) {
    const name = document.createElement("div");
    name.className = "module-name empty";
    name.textContent = "Empty";
    meta.appendChild(name);
  } else if (!m.recognised) {
    const name = document.createElement("div");
    name.className = "module-name";
    name.textContent = "Unrecognised module";
    meta.appendChild(name);
    if (m.raw_firmware) {
      const sub = document.createElement("div");
      sub.className = "module-sub";
      sub.textContent = m.raw_firmware;
      meta.appendChild(sub);
    }
  } else {
    const name = document.createElement("div");
    name.className = "module-name";
    name.textContent = m.module_name;
    meta.appendChild(name);

    const sub = document.createElement("div");
    sub.className = "module-sub";
    sub.textContent = `Article ${m.article} · HW ${m.hardware_version}`;
    meta.appendChild(sub);
  }
  row.appendChild(meta);

  const ver = document.createElement("div");
  ver.className = "module-version";
  if (!m.empty && m.recognised) {
    const fw = document.createElement("div");
    fw.className = "fw";
    fw.textContent = "FW " + m.firmware_version;
    ver.appendChild(fw);

    if (manifest && manifest[m.article]) {
      const latest = manifest[m.article].latest_firmware;
      const badge = document.createElement("span");
      if (latest && latest === m.firmware_version) {
        badge.className = "badge green";
        badge.textContent = "Up to date";
      } else if (latest) {
        badge.className = "badge yellow";
        badge.textContent = "Update: " + latest;
      } else {
        badge.className = "badge gray";
        badge.textContent = "No latest version";
      }
      ver.appendChild(badge);
    } else if (manifest) {
      const badge = document.createElement("span");
      badge.className = "badge gray";
      badge.textContent = "Not in manifest";
      ver.appendChild(badge);
    }
  }
  row.appendChild(ver);

  const chev = document.createElement("div");
  chev.innerHTML = CHEVRON_SVG;
  row.appendChild(chev.firstChild);

  entry.appendChild(row);

  const details = document.createElement("div");
  details.className = "module-details hidden";
  entry.appendChild(details);

  if (!m.empty && m.recognised) {
    let loaded = false;
    row.addEventListener("click", async () => {
      const expanded = row.classList.toggle("expanded");
      details.classList.toggle("hidden", !expanded);
      if (expanded && !loaded) {
        loaded = true;
        await load_pinning(details, m.article, m.slot);
      }
    });
  }

  return entry;
}

async function load_pinning(detailsEl, article, slot) {
  detailsEl.innerHTML = '<div class="muted" style="padding:10px 4px;">Loading pinning…</div>';
  let resp;
  try {
    resp = await (await fetch(`/api/get_module_pinning?article=${encodeURIComponent(article)}&slot=${encodeURIComponent(slot)}`)).json();
  } catch (err) {
    detailsEl.innerHTML = `<div class="fail" style="margin:8px 0;">Failed to load pinning: ${err}</div>`;
    return;
  }

  if (resp.err) {
    detailsEl.innerHTML = `<div class="muted" style="padding:10px 4px;">${resp.err}</div>`;
    return;
  }

  detailsEl.textContent = "";

  const meta = document.createElement("div");
  meta.className = "pinning-meta";
  meta.textContent = `Connector pinout for ${resp.slot_label}`
    + (resp.platform ? ` (${resp.platform})` : "");
  detailsEl.appendChild(meta);

  if (resp.note) {
    const note = document.createElement("div");
    note.className = "muted";
    note.style.padding = "10px 4px";
    note.textContent = resp.note;
    detailsEl.appendChild(note);
    return;
  }

  const body = document.createElement("div");
  body.className = "pinning-body";

  if (resp.connector_image) {
    const wrap = document.createElement("div");
    wrap.className = "connector-image-wrap";
    const img = document.createElement("img");
    img.className = "connector-image";
    img.src = resp.connector_image;
    img.alt = `Connector for ${resp.slot_label}`;
    img.loading = "lazy";
    wrap.appendChild(img);
    body.appendChild(wrap);
  }

  const tableWrap = document.createElement("div");
  const table = document.createElement("table");
  table.className = "pinning-table";
  table.innerHTML = "<thead><tr><th>Pin</th><th>Function</th><th>Description</th></tr></thead>";
  const tbody = document.createElement("tbody");
  for (const p of resp.pins) {
    const tr = document.createElement("tr");

    const pinTd = document.createElement("td");
    pinTd.className = "pin-cell";
    pinTd.textContent = p.pin || "—";
    tr.appendChild(pinTd);

    const fnTd = document.createElement("td");
    fnTd.className = "func-cell";
    fnTd.textContent = p.function;
    tr.appendChild(fnTd);

    const descTd = document.createElement("td");
    descTd.className = "desc-cell";
    descTd.textContent = p.description;
    tr.appendChild(descTd);

    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  body.appendChild(tableWrap);

  // If we have no connector image, the grid will leave a gap; collapse to single column.
  if (!resp.connector_image) body.style.gridTemplateColumns = "1fr";

  detailsEl.appendChild(body);
}

async function render_modules() {
  const summaryEl = document.getElementById("modules-summary");
  const listEl = document.getElementById("modules");
  listEl.textContent = "";
  summaryEl.textContent = "Loading…";

  let modulesResp, manifestResp;
  try {
    [modulesResp, manifestResp] = await Promise.all([
      fetch("/api/get_modules").then(r => r.json()),
      fetch("/api/get_modules_manifest").then(r => r.json()),
    ]);
  } catch (err) {
    summaryEl.innerHTML = `<span class="fail">Failed to load modules: ${err}</span>`;
    return;
  }

  if (modulesResp.err) {
    summaryEl.innerHTML = `<span class="fail">${modulesResp.err}</span>`;
    return;
  }

  const modules = modulesResp.modules || [];
  const manifest = manifestResp && manifestResp.manifest ? manifestResp.manifest : null;

  // Platform header
  if (modulesResp.platform) {
    const card = document.getElementById("platform-card");
    const img = document.getElementById("platform-image");
    document.getElementById("platform-name").textContent = modulesResp.platform;
    document.getElementById("platform-sub").textContent =
      `Slot prefix ${modulesResp.slot_prefix} · ${modules.length} module slot${modules.length === 1 ? "" : "s"}`;
    if (modulesResp.platform_image) {
      img.src = modulesResp.platform_image;
      img.alt = modulesResp.platform;
      img.hidden = false;
    }
    card.hidden = false;
  }

  if (manifestResp && manifestResp.err) {
    summaryEl.textContent = manifest
      ? "Could not refresh latest firmware versions; showing cached data."
      : "No internet — cannot check for module firmware updates.";
  } else if (manifest) {
    summaryEl.textContent = "Latest firmware versions retrieved from firmware.gocontroll.com. Click a module for connector pinout.";
  } else {
    summaryEl.textContent = "Click a module for connector pinout.";
  }

  if (modules.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.style.padding = "14px 4px";
    empty.textContent = "No module slots reported.";
    listEl.appendChild(empty);
    return;
  }

  for (const m of modules) {
    listEl.appendChild(render_module_entry(m, manifest));
  }
}

document.addEventListener("DOMContentLoaded", render_modules, false);
