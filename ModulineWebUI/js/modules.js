const CHEVRON_SVG = '<svg class="module-chevron" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5"/></svg>';

// Warn before leaving the page (sidebar nav, refresh, close) when any open
// configuration form has unsaved changes.
window.addEventListener("beforeunload", (e) => {
  if (document.querySelector('.mod-pane[data-config-dirty="1"]')) {
    e.preventDefault();
    e.returnValue = "";
  }
});

function confirm_discard_if_dirty(pane) {
  if (pane && pane.dataset.configDirty === "1") {
    return confirm("Configuration has unsaved changes. Discard them?");
  }
  return true;
}

// Per-field save-state helpers. Each .ch-input / .ch-select carries a
// `data-saved-value` reflecting the last value written to modules.json,
// and a .clean / .dirty class so CSS can colour it green vs. orange.
function _field_value(el) {
  return el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value;
}
function _mark_field_state(el) {
  if (_field_value(el) === el.dataset.savedValue) {
    el.classList.add("clean");
    el.classList.remove("dirty");
  } else {
    el.classList.add("dirty");
    el.classList.remove("clean");
  }
}
function snapshot_config_fields(pane) {
  for (const el of pane.querySelectorAll(".ch-input, .ch-select")) {
    el.dataset.savedValue = _field_value(el);
    _mark_field_state(el);
  }
}
function update_pane_dirty(pane) {
  pane.dataset.configDirty =
    pane.querySelector(".ch-input.dirty, .ch-select.dirty") ? "1" : "0";
}
function revert_config_fields(pane) {
  const reverted_funcs = [];
  for (const el of pane.querySelectorAll(".ch-input.dirty, .ch-select.dirty")) {
    if (el.type === "checkbox") {
      el.checked = el.dataset.savedValue === "1";
    } else {
      el.value = el.dataset.savedValue;
    }
    _mark_field_state(el);
    if (el.dataset.chKey === "func") reverted_funcs.push(el);
  }
  // Re-fire change on any reverted func selects so update_conditional_cells
  // re-evaluates which channel cells should be enabled/disabled.
  for (const el of reverted_funcs) {
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }
  update_pane_dirty(pane);
}

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
    name.textContent = "Not installed";
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
    let setup_done = false;
    row.addEventListener("click", () => {
      // About to collapse? Confirm if the config form has unsaved changes.
      if (row.classList.contains("expanded")) {
        const dirty_pane = details.querySelector('.mod-pane[data-config-dirty="1"]');
        if (dirty_pane && !confirm_discard_if_dirty(dirty_pane)) return;
        if (dirty_pane) revert_config_fields(dirty_pane);
      }
      const expanded = row.classList.toggle("expanded");
      details.classList.toggle("hidden", !expanded);
      if (expanded && !setup_done) {
        setup_done = true;
        setup_module_detail_tabs(details, m);
      }
    });
  }

  return entry;
}

// ---------------------------------------------------------------------------
// Tabbed detail panel  (Pinout | Configuration)
// ---------------------------------------------------------------------------

function setup_module_detail_tabs(detailsEl, m) {
  // Module info banner (firmware string + QR codes when present).
  // Manufacturer index is intentionally not displayed (internal field).
  const hasQR = (m.qr_front && m.qr_front !== 0) || (m.qr_back && m.qr_back !== 0);
  if (m.raw_firmware || hasQR) {
    const info = document.createElement("div");
    info.className = "mod-info-banner";
    const items = [];
    if (m.raw_firmware) items.push(`<span class="mod-info-item"><span class="k">Firmware</span><span class="v">${m.raw_firmware}</span></span>`);
    if (m.qr_front)    items.push(`<span class="mod-info-item"><span class="k">QR front</span><span class="v">${m.qr_front}</span></span>`);
    if (m.qr_back)     items.push(`<span class="mod-info-item"><span class="k">QR back</span><span class="v">${m.qr_back}</span></span>`);
    info.innerHTML = items.join("");
    detailsEl.appendChild(info);
  }

  const tabBar = document.createElement("div");
  tabBar.className = "mod-tabs";

  const pinoutBtn = document.createElement("button");
  pinoutBtn.className = "mod-tab active";
  pinoutBtn.textContent = "Pinout";

  const configBtn = document.createElement("button");
  configBtn.className = "mod-tab";
  configBtn.textContent = "Configuration";

  tabBar.appendChild(pinoutBtn);
  tabBar.appendChild(configBtn);
  detailsEl.appendChild(tabBar);

  const pinoutPane = document.createElement("div");
  pinoutPane.className = "mod-pane";
  detailsEl.appendChild(pinoutPane);

  const configPane = document.createElement("div");
  configPane.className = "mod-pane hidden";
  detailsEl.appendChild(configPane);

  let config_loaded = false;

  // Load pinout immediately on first expand.
  load_pinning(pinoutPane, m.article, m.slot);

  pinoutBtn.addEventListener("click", () => {
    // Leaving the Configuration tab with unsaved changes?
    if (!configPane.classList.contains("hidden")
        && !confirm_discard_if_dirty(configPane)) return;
    revert_config_fields(configPane);
    pinoutBtn.classList.add("active");
    configBtn.classList.remove("active");
    pinoutPane.classList.remove("hidden");
    configPane.classList.add("hidden");
  });

  configBtn.addEventListener("click", async () => {
    configBtn.classList.add("active");
    pinoutBtn.classList.remove("active");
    configPane.classList.remove("hidden");
    pinoutPane.classList.add("hidden");
    if (!config_loaded) {
      config_loaded = true;
      await load_module_config(configPane, m.slot);
    }
  });
}

// ---------------------------------------------------------------------------
// Pinout tab
// ---------------------------------------------------------------------------

async function load_pinning(pane, article, slot) {
  pane.innerHTML = '<div class="muted" style="padding:10px 4px;">Loading pinning…</div>';
  let resp;
  try {
    resp = await (await fetch(`/api/get_module_pinning?article=${encodeURIComponent(article)}&slot=${encodeURIComponent(slot)}`)).json();
  } catch (err) {
    pane.innerHTML = `<div class="fail" style="margin:8px 0;">Failed to load pinning: ${err}</div>`;
    return;
  }

  if (resp.err) {
    pane.innerHTML = `<div class="muted" style="padding:10px 4px;">${resp.err}</div>`;
    return;
  }

  pane.textContent = "";

  if (resp.note) {
    const note = document.createElement("div");
    note.className = "muted";
    note.style.padding = "10px 4px";
    note.textContent = resp.note;
    pane.appendChild(note);
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

  if (!resp.connector_image) body.style.gridTemplateColumns = "1fr";

  pane.appendChild(body);
}

// ---------------------------------------------------------------------------
// Configuration tab
// ---------------------------------------------------------------------------

async function load_module_config(pane, slot) {
  pane.innerHTML = '<div class="muted" style="padding:10px 4px;">Loading configuration…</div>';
  let resp;
  try {
    resp = await fetch(`/api/get_module_config?slot=${encodeURIComponent(slot)}`).then(r => r.json());
  } catch (err) {
    pane.innerHTML = `<div class="fail" style="margin:8px 0;">Failed to load configuration: ${err}</div>`;
    return;
  }
  if (resp.err) {
    pane.innerHTML = `<div class="muted" style="padding:10px 4px;">${resp.err}</div>`;
    return;
  }
  render_module_config(pane, resp);
}

function render_driver_toggle(pane, slot, initialEnabled) {
  const section = document.createElement("div");
  section.className = "mod-config-section";
  section.textContent = "Hardware driver";
  pane.appendChild(section);

  const row = document.createElement("div");
  row.className = "mod-config-row driver-row";

  const lbl = document.createElement("label");
  lbl.className = "mod-config-label";
  lbl.textContent = "Driver controls slot";

  const wrap = document.createElement("label");
  wrap.className = "driver-toggle";
  wrap.title = "When on, go-hardware-driver resets, initialises and drives "
             + "this slot cyclically. When off, the module is left untouched "
             + "so another application can drive it.";

  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = initialEnabled;

  const slider = document.createElement("span");
  slider.className = "driver-toggle-slider";

  const stateText = document.createElement("span");
  stateText.className = "driver-toggle-label";
  stateText.textContent = cb.checked ? "Enabled" : "Disabled";

  wrap.appendChild(cb);
  wrap.appendChild(slider);
  wrap.appendChild(stateText);

  const feedback = document.createElement("span");
  feedback.className = "mod-save-feedback";

  cb.addEventListener("change", async () => {
    const desired = cb.checked;
    cb.disabled = true;
    feedback.className = "mod-save-feedback";
    feedback.textContent = "";
    try {
      const resp = await fetch("/api/set_module_enabled", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot, enabled: desired }),
      }).then(r => r.json());
      if (resp.err) {
        cb.checked = !desired;
        feedback.className = "mod-save-feedback fail";
        feedback.textContent = resp.err;
      } else {
        stateText.textContent = desired ? "Enabled" : "Disabled";
        feedback.className = "mod-save-feedback ok";
        feedback.textContent = "Saved — restart go-hardware-driver to apply";
        setTimeout(() => {
          if (feedback.classList.contains("ok")) feedback.textContent = "";
        }, 4000);
      }
    } catch (err) {
      cb.checked = !desired;
      feedback.className = "mod-save-feedback fail";
      feedback.textContent = `Save failed: ${err}`;
    } finally {
      cb.disabled = false;
    }
  });

  row.appendChild(lbl);
  row.appendChild(wrap);
  row.appendChild(feedback);
  pane.appendChild(row);
}

function render_module_config(pane, cfg) {
  pane.textContent = "";
  pane.dataset.configDirty = "0";

  // Driver-enable toggle. Lives outside the dirty-state form: changes save
  // immediately via /api/set_module_enabled so a half-finished edit elsewhere
  // doesn't accidentally apply, and toggling never raises the "unsaved
  // changes" warning.
  render_driver_toggle(pane, cfg.slot, cfg.enabled !== false);

  const schema = cfg.schema;
  if (!schema) {
    const msg = document.createElement("div");
    msg.className = "muted";
    msg.style.padding = "10px 4px";
    msg.textContent = "No configuration schema available for this module type.";
    pane.appendChild(msg);
    return;
  }

  // Label
  const labelSection = document.createElement("div");
  labelSection.className = "mod-config-section";
  labelSection.textContent = "Label";
  pane.appendChild(labelSection);

  const labelRow = document.createElement("div");
  labelRow.className = "mod-config-row";
  const labelLbl = document.createElement("label");
  labelLbl.className = "mod-config-label";
  labelLbl.textContent = "Description";
  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.className = "ch-input";
  labelInput.value = cfg.label || "";
  labelInput.placeholder = "Optional slot label";
  labelRow.appendChild(labelLbl);
  labelRow.appendChild(labelInput);
  pane.appendChild(labelRow);

  // Module-level fields
  const modFields = schema.module_fields || {};
  if (Object.keys(modFields).length > 0) {
    const modSection = document.createElement("div");
    modSection.className = "mod-config-section";
    modSection.textContent = "Module settings";
    pane.appendChild(modSection);

    for (const [key, spec] of Object.entries(modFields)) {
      if (spec.type === "freq_pairs") {
        render_freq_pairs(pane, key, spec, cfg.module[key] || spec.default);
      } else if (spec.type === "bool_array") {
        render_bool_array(pane, key, spec, cfg.module[key] || spec.default);
      } else if (spec.type === "enum") {
        const row = document.createElement("div");
        row.className = "mod-config-row";
        const lbl = document.createElement("label");
        lbl.className = "mod-config-label";
        lbl.textContent = spec.label || key;
        const sel = document.createElement("select");
        sel.className = "ch-select";
        sel.dataset.modKey = key;
        const cur = cfg.module[key] !== undefined ? cfg.module[key] : spec.default;
        const labels = spec.value_labels || {};
        for (const v of spec.values) {
          const opt = document.createElement("option");
          opt.value = v;
          opt.textContent = labels[v] || v;
          if (cur === v) opt.selected = true;
          sel.appendChild(opt);
        }
        row.appendChild(lbl);
        row.appendChild(sel);
        pane.appendChild(row);
      }
    }
  }

  // Channel settings
  const chFields = schema.channel_fields || [];
  if (chFields.length > 0 && cfg.channels.length > 0) {
    const chSection = document.createElement("div");
    chSection.className = "mod-config-section";
    chSection.textContent = "Channel settings";
    pane.appendChild(chSection);
    render_channel_table(pane, chFields, cfg.channels);
  }

  // Save row
  const saveRow = document.createElement("div");
  saveRow.className = "mod-save-row";
  const saveBtn = document.createElement("button");
  saveBtn.className = "btn primary";
  saveBtn.textContent = "Save";
  const feedback = document.createElement("span");
  feedback.className = "mod-save-feedback";
  saveRow.appendChild(saveBtn);
  saveRow.appendChild(feedback);
  pane.appendChild(saveRow);

  // Snapshot the freshly-rendered values; everything starts in the clean
  // (green) state. On input/change we recolour the touched field and recompute
  // the pane-level dirty flag — so reverting to the saved value also clears
  // the unsaved-changes warning.
  snapshot_config_fields(pane);
  const mark_dirty = (e) => {
    const tgt = e.target;
    if (!tgt || !tgt.classList) return;
    if (!tgt.classList.contains("ch-input") && !tgt.classList.contains("ch-select")) return;
    _mark_field_state(tgt);
    update_pane_dirty(pane);
  };
  pane.addEventListener("input", mark_dirty);
  pane.addEventListener("change", mark_dirty);

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    feedback.textContent = "";
    feedback.className = "mod-save-feedback";

    const payload = {
      slot: cfg.slot,
      label: labelInput.value.trim(),
      module: collect_module_fields(pane, schema, cfg.module),
      channels: collect_channel_fields(pane, schema, cfg.channels),
    };

    try {
      const resp = await fetch("/api/save_module_config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(r => r.json());

      if (resp.err) {
        feedback.className = "mod-save-feedback fail";
        feedback.textContent = resp.err;
      } else {
        feedback.className = "mod-save-feedback ok";
        feedback.textContent = "Saved";
        snapshot_config_fields(pane);
        pane.dataset.configDirty = "0";
        setTimeout(() => { if (feedback.textContent === "Saved") feedback.textContent = ""; }, 3000);
      }
    } catch (err) {
      feedback.className = "mod-save-feedback fail";
      feedback.textContent = `Save failed: ${err}`;
    } finally {
      saveBtn.disabled = false;
    }
  });
}

function render_freq_pairs(pane, key, spec, currentValues) {
  const wrap = document.createElement("div");
  wrap.className = "mod-config-subsection";

  const sublbl = document.createElement("div");
  sublbl.className = "mod-config-sublabel";
  sublbl.textContent = spec.label || key;
  wrap.appendChild(sublbl);

  for (let i = 0; i < spec.length; i++) {
    const row = document.createElement("div");
    row.className = "mod-config-row";

    const lbl = document.createElement("label");
    lbl.className = "mod-config-label";
    lbl.textContent = (spec.pair_labels && spec.pair_labels[i]) || `Pair ${i + 1}`;

    const sel = document.createElement("select");
    sel.className = "ch-select";
    sel.dataset.fpKey = key;
    sel.dataset.fpIdx = String(i);
    const curVal = Array.isArray(currentValues) ? (currentValues[i] !== undefined ? currentValues[i] : spec.default[i]) : spec.default[i];
    const labels = spec.value_labels || {};
    for (const v of spec.values) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = labels[v] || v;
      if (curVal === v) opt.selected = true;
      sel.appendChild(opt);
    }

    row.appendChild(lbl);
    row.appendChild(sel);
    wrap.appendChild(row);
  }
  pane.appendChild(wrap);
}

function render_bool_array(pane, key, spec, currentValues) {
  // "rows" mode: render each item as a labeled mod-config-row with an on/off
  // dropdown (matches the look of sensor_supply_* enum fields).
  if (spec.display === "rows") {
    const offText = spec.off_label || "Off";
    const onText  = spec.on_label  || "On";
    for (let i = 0; i < spec.length; i++) {
      const row = document.createElement("div");
      row.className = "mod-config-row";

      const lbl = document.createElement("label");
      lbl.className = "mod-config-label";
      lbl.textContent = (spec.row_label_prefix || "") + (i + 1);

      const sel = document.createElement("select");
      sel.className = "ch-select";
      sel.dataset.baKey = key;
      sel.dataset.baIdx = String(i);
      const cur = Array.isArray(currentValues) ? Boolean(currentValues[i]) : false;

      const offOpt = document.createElement("option");
      offOpt.value = "off";
      offOpt.textContent = offText;
      if (!cur) offOpt.selected = true;
      sel.appendChild(offOpt);

      const onOpt = document.createElement("option");
      onOpt.value = "on";
      onOpt.textContent = onText;
      if (cur) onOpt.selected = true;
      sel.appendChild(onOpt);

      row.appendChild(lbl);
      row.appendChild(sel);
      pane.appendChild(row);
    }
    return;
  }

  // Default: compact checkbox row labeled 1..N.
  const wrap = document.createElement("div");
  wrap.className = "mod-config-subsection";

  const sublbl = document.createElement("div");
  sublbl.className = "mod-config-sublabel";
  sublbl.textContent = spec.label || key;
  wrap.appendChild(sublbl);

  const cbRow = document.createElement("div");
  cbRow.className = "mod-config-bool-row";
  for (let i = 0; i < spec.length; i++) {
    const item = document.createElement("label");
    item.className = "mod-config-bool-item";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.baKey = key;
    cb.dataset.baIdx = String(i);
    cb.checked = Array.isArray(currentValues) ? Boolean(currentValues[i]) : false;

    const span = document.createElement("span");
    span.textContent = String(i + 1);

    item.appendChild(cb);
    item.appendChild(span);
    cbRow.appendChild(item);
  }
  wrap.appendChild(cbRow);
  pane.appendChild(wrap);
}

function render_channel_table(pane, fields, channels) {
  const tableWrap = document.createElement("div");
  tableWrap.className = "ch-table-wrap";

  const table = document.createElement("table");
  table.className = "channel-config-table";

  // Header
  const thead = document.createElement("thead");
  const htr = document.createElement("tr");
  const chTh = document.createElement("th");
  chTh.textContent = "Ch";
  htr.appendChild(chTh);
  for (const f of fields) {
    if (f.hidden) continue;
    const th = document.createElement("th");
    th.textContent = f.unit ? `${f.label} (${f.unit})` : f.label;
    htr.appendChild(th);
  }
  thead.appendChild(htr);
  table.appendChild(thead);

  // Rows
  const tbody = document.createElement("tbody");
  for (const ch of channels) {
    const tr = document.createElement("tr");
    tr.dataset.channel = String(ch.channel);

    const numTd = document.createElement("td");
    numTd.className = "ch-num";
    numTd.textContent = String(ch.channel);
    tr.appendChild(numTd);

    let funcSelect = null;

    for (const f of fields) {
      if (f.hidden) continue;
      const td = document.createElement("td");
      td.dataset.field = f.key;
      if (f.when_func) td.dataset.whenFunc = f.when_func.join(",");

      if (f.type === "enum") {
        const sel = document.createElement("select");
        sel.className = "ch-select";
        sel.dataset.chKey = f.key;
        const curVal = ch[f.key] !== undefined ? ch[f.key] : f.default;
        const labels = f.value_labels || {};
        for (const v of f.values) {
          const opt = document.createElement("option");
          opt.value = v;
          opt.textContent = labels[v] || v;
          if (curVal === v) opt.selected = true;
          sel.appendChild(opt);
        }
        if (f.key === "func") funcSelect = sel;
        td.appendChild(sel);
      } else if (f.type === "int") {
        const inp = document.createElement("input");
        inp.type = "number";
        inp.className = "ch-input";
        inp.dataset.chKey = f.key;
        inp.min = String(f.min);
        inp.max = String(f.max);
        inp.value = String(ch[f.key] !== undefined ? ch[f.key] : f.default);
        td.appendChild(inp);
      } else if (f.type === "string") {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.className = "ch-input ch-input-text";
        inp.dataset.chKey = f.key;
        if (f.max_length) inp.maxLength = f.max_length;
        if (f.placeholder) inp.placeholder = f.placeholder;
        inp.value = ch[f.key] !== undefined && ch[f.key] !== null ? String(ch[f.key]) : f.default;
        td.appendChild(inp);
      }
      tr.appendChild(td);
    }

    tbody.appendChild(tr);

    if (funcSelect) {
      const captured_tr = tr;
      update_conditional_cells(captured_tr, funcSelect.value, fields);
      funcSelect.addEventListener("change", () => {
        update_conditional_cells(captured_tr, funcSelect.value, fields);
      });
    }
  }

  table.appendChild(tbody);
  tableWrap.appendChild(table);
  pane.appendChild(tableWrap);
}

function update_conditional_cells(tr, funcValue, fields) {
  for (const f of fields) {
    if (!f.when_func) continue;
    const td = tr.querySelector(`td[data-field="${f.key}"]`);
    if (!td) continue;
    const applicable = f.when_func.includes(funcValue);
    td.classList.toggle("ch-inactive", !applicable);
    const inp = td.querySelector("input, select");
    if (inp) inp.disabled = !applicable;
  }
}

// ---------------------------------------------------------------------------
// Collect form values for save payload
// ---------------------------------------------------------------------------

function collect_module_fields(pane, schema, originalModule) {
  const result = Object.assign({}, originalModule);
  for (const [key, spec] of Object.entries(schema.module_fields || {})) {
    if (spec.type === "enum") {
      const sel = pane.querySelector(`select[data-mod-key="${key}"]`);
      if (sel) result[key] = sel.value;
    } else if (spec.type === "freq_pairs") {
      const sels = Array.from(pane.querySelectorAll(`select[data-fp-key="${key}"]`))
        .sort((a, b) => Number(a.dataset.fpIdx) - Number(b.dataset.fpIdx));
      if (sels.length > 0) result[key] = sels.map(s => s.value);
    } else if (spec.type === "bool_array") {
      if (spec.display === "rows") {
        const sels = Array.from(pane.querySelectorAll(`select[data-ba-key="${key}"]`))
          .sort((a, b) => Number(a.dataset.baIdx) - Number(b.dataset.baIdx));
        if (sels.length > 0) result[key] = sels.map(s => s.value === "on");
      } else {
        const cbs = Array.from(pane.querySelectorAll(`input[data-ba-key="${key}"]`))
          .sort((a, b) => Number(a.dataset.baIdx) - Number(b.dataset.baIdx));
        if (cbs.length > 0) result[key] = cbs.map(c => c.checked);
      }
    }
  }
  return result;
}

function collect_channel_fields(pane, schema, originalChannels) {
  const tbody = pane.querySelector(".channel-config-table tbody");
  if (!tbody) return originalChannels;

  const chFields = schema.channel_fields || [];
  const result = [];

  for (const tr of tbody.rows) {
    const chNum = parseInt(tr.dataset.channel, 10);
    const orig = originalChannels.find(c => c.channel === chNum) || {};
    const entry = { channel: chNum };

    for (const f of chFields) {
      // Hidden fields are not in the DOM — preserve the value the JSON had
      // (or omit the key if it wasn't there) so the editor doesn't change it.
      if (f.hidden) {
        if (orig[f.key] !== undefined) entry[f.key] = orig[f.key];
        continue;
      }

      const td = tr.querySelector(`td[data-field="${f.key}"]`);
      if (!td) continue;

      if (f.type === "enum") {
        const sel = td.querySelector("select");
        entry[f.key] = sel ? sel.value : (orig[f.key] !== undefined ? orig[f.key] : f.default);
      } else if (f.type === "int") {
        const inp = td.querySelector("input");
        if (inp && !inp.disabled) {
          const parsed = parseInt(inp.value, 10);
          entry[f.key] = isNaN(parsed) ? f.default : parsed;
        } else {
          entry[f.key] = orig[f.key] !== undefined ? orig[f.key] : f.default;
        }
      } else if (f.type === "string") {
        const inp = td.querySelector("input");
        entry[f.key] = inp ? inp.value : (orig[f.key] !== undefined ? orig[f.key] : f.default);
      }
    }
    result.push(entry);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

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

  if (manifestResp && manifestResp.err) {
    summaryEl.textContent = manifest
      ? "Could not refresh latest firmware versions; showing cached data."
      : "No internet — cannot check for module firmware updates.";
  } else if (manifest) {
    summaryEl.textContent = "Latest firmware versions retrieved from firmware.gocontroll.com. Click a module for details.";
  } else {
    summaryEl.textContent = "Click a module for connector pinout and configuration.";
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
