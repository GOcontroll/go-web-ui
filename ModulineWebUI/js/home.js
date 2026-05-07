document.addEventListener('DOMContentLoaded', async function () {
  const sn_request = fetch("/api/get_serial_number");
  const software_request = fetch('/api/get_software');
  const platform_request = fetch("/api/get_platform");
  const hardware_request = fetch("/api/get_hardware");
  const rootfs_request = fetch("/api/get_rootfs_build");
  const simulink_request = fetch('/api/get_sim_ver');
  render_controller_pinning();

  var res = await (await sn_request).json();
  if (res.err) {
    document.getElementById("serial_number").innerText = "Not found";
    console.log(res.err);
  } else {
    document.getElementById("serial_number").innerText = res.sn;
  }

  res = await (await software_request).json();
  if (res.err) {
    document.getElementById("controller_software").innerText = "Not found";
    console.log(res.err);
  } else {
    document.getElementById("controller_software").innerText = res.version;
  }

  // Prefer platform; fall back to hardware when platform is unavailable.
  const platform_res = await (await platform_request).json();
  if (!platform_res.err && platform_res.platform) {
    document.getElementById("controller_hardware").innerText = platform_res.platform;
  } else {
    if (platform_res.err) console.log(platform_res.err);
    const hardware_res = await (await hardware_request).json();
    if (hardware_res.err) {
      document.getElementById("controller_hardware").innerText = "Not found";
      console.log(hardware_res.err);
    } else {
      document.getElementById("controller_hardware").innerText = hardware_res.hardware;
    }
  }

  // Rootfs build — combine sha + date + variant/arch into one line
  const rootfs_res = await (await rootfs_request).json();
  if (rootfs_res.err) {
    document.getElementById("rootfs_build").innerText = "Not found";
    console.log(rootfs_res.err);
  } else {
    const main = [];
    if (rootfs_res.build_sha)  main.push(rootfs_res.build_sha);
    if (rootfs_res.build_date) main.push(rootfs_res.build_date.split("T")[0]);
    let line = main.join(" · ");
    const ctx = [];
    if (rootfs_res.variant) ctx.push(rootfs_res.variant);
    if (rootfs_res.rootfs)  ctx.push(rootfs_res.rootfs);
    if (ctx.length) line += ` (${ctx.join(" · ")})`;
    document.getElementById("rootfs_build").innerText = line || "—";
  }

  res = await (await simulink_request).json();
  if (res.err) {
    document.getElementById("simulink_version").innerText = "Not found";
    console.log(res.err);
  } else {
    document.getElementById("simulink_version").innerText = res.version;
  }
}, false);


async function render_controller_pinning() {
  const card = document.getElementById("controller-pinning-card");
  if (!card) return;
  let resp;
  try {
    resp = await (await fetch("/api/get_controller_pinning")).json();
  } catch (err) {
    console.log("controller pinning fetch failed:", err);
    return;
  }
  if (resp.err) {
    console.log("controller pinning:", resp.err);
    return;
  }

  const title = document.getElementById("controller-pinning-title");
  title.textContent = "Controller pinning · " + (resp.connector_label || resp.platform);

  const desc = document.getElementById("controller-pinning-desc");
  if (resp.description) {
    desc.textContent = resp.description;
    desc.hidden = false;
  } else {
    desc.hidden = true;
  }

  const wrap = document.getElementById("controller-image-wrap");
  const img = document.getElementById("controller-connector-image");
  if (resp.connector_image) {
    img.src = resp.connector_image;
    img.alt = resp.connector_label || "Controller connector";
    wrap.hidden = false;
  } else {
    wrap.hidden = true;
    document.getElementById("controller-pinning-body").style.gridTemplateColumns = "1fr";
  }

  const tbody = document.getElementById("controller-pinning-tbody");
  tbody.textContent = "";
  for (const p of (resp.pins || [])) {
    const tr = document.createElement("tr");
    const pinTd = document.createElement("td");
    pinTd.className = "pin-cell";
    pinTd.textContent = p.pin;
    tr.appendChild(pinTd);
    const sigTd = document.createElement("td");
    sigTd.className = "func-cell";
    sigTd.textContent = p.signal;
    tr.appendChild(sigTd);
    const descTd = document.createElement("td");
    descTd.className = "desc-cell";
    descTd.textContent = p.description;
    tr.appendChild(descTd);
    tbody.appendChild(tr);
  }
  card.hidden = false;
}


function alert_class_switch(elem, newClass) {
  elem.classList.remove("ok", "info", "fail");
  elem.classList.add(newClass, "fade-in");
  setTimeout(() => {
    elem.classList.remove("fade-in");
  }, 500);
}

function confirmPasswordChange() {
  return new Promise(resolve => {
    let resolved = false;
    const safe = v => { if (!resolved) { resolved = true; resolve(v); } };
    const overlay = showModal({
      title: "Change Web UI password?",
      variant: "warn",
      body: `<p>You are about to change the password used to log in to this Web UI on this controller.</p>
             <p><strong>If you lose this password the Web UI is no longer accessible.</strong>
                Recovery requires alternative access to the controller (Ethernet shell, USB console, …) to reset
                <code>pass_hash</code> in <code>/etc/go_webui.conf</code> manually.</p>
             <p>Make sure you remember the new password before continuing.</p>`,
      actions: [
        { label: "Cancel",          onClick: () => safe(false) },
        { label: "Change password", primary: true, onClick: () => safe(true) },
      ],
    });
    const obs = new MutationObserver(() => {
      if (!overlay.parentNode) { obs.disconnect(); safe(false); }
    });
    obs.observe(document.body, { childList: true });
  });
}

async function set_passkey() {
  const pass1 = document.getElementById("passkey1");
  const pass2 = document.getElementById("passkey2");
  const result = document.getElementById("new_passkey_result");
  if (pass1.value != pass2.value) {
    result.innerText = "Could not change password: entries don't match.";
    alert_class_switch(result, "info");
    return;
  }
  if (!(pass1.value.length > 6)) {
    result.innerText = "Could not change password: must be longer than 6 characters.";
    alert_class_switch(result, "info");
    return;
  }
  const ok = await confirmPasswordChange();
  if (!ok) return;
  try {
    const response = await post_json("/api/set_passkey", { "passkey": pass1.value });
    if (response.err) {
      result.innerText = response.err;
      alert_class_switch(result, "fail");
      console.log(response.deets);
      return;
    }
    result.innerText = "Password changed. Use the new password on your next login.";
    pass1.value = "";
    pass2.value = "";
    alert_class_switch(result, "ok");
    return
  } catch (err) {
    result.innerText = "Could not change password: unexpected response from server.";
    alert_class_switch(result, "fail");
    console.log(err);
    return;
  }
}

async function download_a2l() {
  const url = "/api/GOcontroll_Linux.a2l";
  try {
    const resp = await fetch(url);
    if (resp.ok) {
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = "GOcontroll_Linux.a2l";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
      return;
    }
    let msg = "The .a2l file could not be downloaded.";
    try {
      const j = await resp.json();
      if (j && j.err) msg = j.err;
    } catch (_) { /* response was not JSON */ }
    showModal({
      title: "a2l file unavailable",
      variant: "warn",
      body: `<p>${msg}</p>`,
    });
  } catch (err) {
    showModal({
      title: "Download failed",
      variant: "danger",
      body: `<p>The browser could not reach the server.</p>
             <p class="muted mono" style="font-size:12px;">${String(err)}</p>`,
    });
  }
}

async function toggle_pass() {
  const pass1 = document.getElementById("passkey1");
  const pass2 = document.getElementById("passkey2");
  if (pass1.getAttribute("type") === "password") {
    pass1.setAttribute("type", "text");
    pass2.setAttribute("type", "text");
  } else if (pass1.getAttribute("type") === "text") {
    pass1.setAttribute("type", "password");
    pass2.setAttribute("type", "password");
  }
}