function alert_class_switch(elem, newClass) {
  elem.classList.remove("ok", "info", "fail");
  elem.classList.add(newClass, "fade-in");
  setTimeout(() => {
    elem.classList.remove("fade-in");
  }, 500);
  setTimeout(() => {
    elem.classList.remove("ok", "info", "fail");
    elem.innerText = "";
  }, 5000);
}

async function post_json(url, data) {
  return (await fetch(url,
    {
      method: 'POST',
      body: JSON.stringify(data),
      headers: { "Content-type": "application/json; charset=UTF-8" }
    }
  )).json()
}

// ---------------------------------------------------------------------------
// Modal helper. Usage:
//   showModal({
//     title: "a2l unavailable",
//     variant: "warn",                   // "warn" | "danger" | "info" | undefined
//     body:  "<p>The file is missing.</p>",
//     actions: [
//       { label: "Cancel" },
//       { label: "Retry", primary: true, onClick: () => doRetry() },
//     ],
//   });
// `onClick` returning false keeps the modal open; otherwise it closes after click.
// ---------------------------------------------------------------------------

const MODAL_ICONS = {
  warn:   '<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"/>',
  danger: '<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"/>',
  info:   '<path stroke-linecap="round" stroke-linejoin="round" d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"/>',
};

function showModal({ title, body, actions, variant }) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  const iconPath = variant && MODAL_ICONS[variant];
  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-header${variant ? ' ' + variant : ''}">
        ${iconPath ? `<svg class="icon" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" aria-hidden="true">${iconPath}</svg>` : ''}
        <span>${title || ''}</span>
      </div>
      <div class="modal-body">${body || ''}</div>
      <div class="modal-footer"></div>
    </div>
  `;
  const footer = overlay.querySelector(".modal-footer");
  const acts = (actions && actions.length) ? actions : [{ label: "OK", primary: true }];
  acts.forEach(a => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn" + (a.primary ? " primary" : "") + (a.danger ? " danger" : "");
    btn.textContent = a.label;
    btn.addEventListener("click", () => {
      const r = a.onClick ? a.onClick() : undefined;
      if (r !== false) closeModal(overlay);
    });
    footer.appendChild(btn);
  });
  overlay.addEventListener("click", e => {
    if (e.target === overlay) closeModal(overlay);
  });
  const escHandler = e => { if (e.key === "Escape") closeModal(overlay); };
  document.addEventListener("keydown", escHandler);
  overlay._escHandler = escHandler;
  document.body.appendChild(overlay);
  // Focus the last (typically primary) button so Enter confirms.
  const lastBtn = footer.lastElementChild;
  if (lastBtn) lastBtn.focus();
  return overlay;
}

function closeModal(overlay) {
  if (!overlay || !overlay.parentNode) return;
  if (overlay._escHandler) document.removeEventListener("keydown", overlay._escHandler);
  overlay.remove();
}

// ---------------------------------------------------------------------------
// Append the installed package version to the page footer (if present).
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", async () => {
  const footer = document.querySelector(".app-footer");
  if (!footer) return;
  try {
    const resp = await (await fetch("/api/get_webui_version")).json();
    if (resp && resp.version) {
      footer.textContent = footer.textContent.trimEnd() + "  ·  v" + resp.version;
    }
  } catch (_) { /* keep base footer text on failure */ }
});
