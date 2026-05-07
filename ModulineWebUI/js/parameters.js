// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function alert_class_switch(elem, newClass) {
  elem.classList.remove("ok", "info", "fail");
  elem.classList.add(newClass, "fade-in");
  setTimeout(() => elem.classList.remove("fade-in"), 500);
  setTimeout(() => {
    elem.classList.remove("ok", "info", "fail");
    elem.innerText = "";
  }, 5000);
}

function show_result(id, kind, text) {
  const el = document.getElementById(id);
  if (!el) return;
  el.innerText = text;
  alert_class_switch(el, kind);
}

function make_input(value, cls, placeholder) {
  const inp = document.createElement("input");
  inp.type = "text";
  inp.className = cls;
  inp.value = value || "";
  if (placeholder) inp.placeholder = placeholder;
  return inp;
}

function make_remove_button(tr) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn sm danger";
  btn.title = "Remove row";
  btn.textContent = "×";
  btn.addEventListener("click", () => tr.remove());
  return btn;
}

// ---------------------------------------------------------------------------
// Application configuration (/etc/gocontroll/config.json)
// ---------------------------------------------------------------------------

function make_config_row(key = "", value = "") {
  const tr = document.createElement("tr");

  const tdK = document.createElement("td");
  tdK.appendChild(make_input(key, "config-key", "Key"));
  tr.appendChild(tdK);

  const tdV = document.createElement("td");
  tdV.appendChild(make_input(value, "config-val", "Value"));
  tr.appendChild(tdV);

  const tdRm = document.createElement("td");
  tdRm.appendChild(make_remove_button(tr));
  tr.appendChild(tdRm);

  return tr;
}

function add_config_row() {
  const tbody = document.getElementById("config-tbody");
  const tr = make_config_row();
  tbody.appendChild(tr);
  tr.querySelector(".config-key").focus();
}

async function load_app_config() {
  const tbody = document.getElementById("config-tbody");
  tbody.textContent = "";
  let resp;
  try {
    resp = await (await fetch("/api/get_app_config")).json();
  } catch (err) {
    show_result("config-result", "fail", "Failed to load configuration: " + err);
    return;
  }
  if (resp.err) {
    show_result("config-result", "fail", resp.err);
    return;
  }
  const cfg = resp.config || {};
  const keys = Object.keys(cfg).sort((a, b) => a.localeCompare(b));
  for (const k of keys) {
    tbody.appendChild(make_config_row(k, cfg[k]));
  }
}

async function save_app_config() {
  const rows = document.querySelectorAll("#config-tbody tr");
  const cfg = {};
  const seen = new Set();
  let duplicate = null;
  for (const row of rows) {
    const k = row.querySelector(".config-key").value.trim();
    if (!k) continue;
    if (seen.has(k)) { duplicate = k; break; }
    seen.add(k);
    cfg[k] = row.querySelector(".config-val").value;
  }
  if (duplicate) {
    show_result("config-result", "fail", `Duplicate key: ${duplicate}`);
    return;
  }
  try {
    const resp = await post_json("/api/save_app_config", cfg);
    if (resp.err) {
      show_result("config-result", "fail", resp.err);
      return;
    }
    show_result("config-result", "ok", `Configuration saved (${Object.keys(cfg).length} keys).`);
    await load_app_config();
  } catch (err) {
    show_result("config-result", "fail", "Save failed: " + err);
  }
}

// ---------------------------------------------------------------------------
// Environment variables (/etc/gocontroll/parameters.js)
// ---------------------------------------------------------------------------

function make_env_row(alias = "", env = "", value = "") {
  const tr = document.createElement("tr");

  const tdA = document.createElement("td");
  tdA.appendChild(make_input(alias, "env-alias", "alias"));
  tr.appendChild(tdA);

  const tdE = document.createElement("td");
  tdE.appendChild(make_input(env, "env-name", "ENV_VAR"));
  tr.appendChild(tdE);

  const tdV = document.createElement("td");
  tdV.appendChild(make_input(value, "env-value", "value"));
  tr.appendChild(tdV);

  const tdRm = document.createElement("td");
  tdRm.appendChild(make_remove_button(tr));
  tr.appendChild(tdRm);

  return tr;
}

function add_env_row() {
  const tbody = document.getElementById("env-tbody");
  const tr = make_env_row();
  tbody.appendChild(tr);
  tr.querySelector(".env-alias").focus();
}

async function load_env_parameters() {
  const tbody = document.getElementById("env-tbody");
  tbody.textContent = "";
  let resp;
  try {
    resp = await (await fetch("/api/get_env_parameters")).json();
  } catch (err) {
    show_result("env-result", "fail", "Failed to load environment: " + err);
    return;
  }
  if (resp.err) {
    show_result("env-result", "fail", resp.err);
    return;
  }
  for (const e of (resp.entries || [])) {
    tbody.appendChild(make_env_row(e.alias, e.env, e.value));
  }
}

async function save_env_parameters() {
  const rows = document.querySelectorAll("#env-tbody tr");
  const entries = [];
  const seenAlias = new Set();
  const seenEnv = new Set();
  for (const row of rows) {
    const alias = row.querySelector(".env-alias").value.trim();
    const env = row.querySelector(".env-name").value.trim();
    const value = row.querySelector(".env-value").value;
    if (!alias && !env && !value) continue;
    if (!alias || !env) {
      show_result("env-result", "fail", "Each row needs both an alias and an environment variable name.");
      return;
    }
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(alias)) {
      show_result("env-result", "fail", `Invalid alias: ${alias}`);
      return;
    }
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(env)) {
      show_result("env-result", "fail", `Invalid environment variable name: ${env}`);
      return;
    }
    if (seenAlias.has(alias)) {
      show_result("env-result", "fail", `Duplicate alias: ${alias}`);
      return;
    }
    if (seenEnv.has(env)) {
      show_result("env-result", "fail", `Duplicate environment variable: ${env}`);
      return;
    }
    seenAlias.add(alias);
    seenEnv.add(env);
    entries.push({ alias, env, value });
  }
  try {
    const resp = await post_json("/api/save_env_parameters", entries);
    if (resp.err) {
      show_result("env-result", "fail", resp.err);
      return;
    }
    show_result("env-result", "ok", `Environment saved (${entries.length} entries).`);
    await load_env_parameters();
  } catch (err) {
    show_result("env-result", "fail", "Save failed: " + err);
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", async () => {
  await Promise.all([load_app_config(), load_env_parameters()]);
}, false);
