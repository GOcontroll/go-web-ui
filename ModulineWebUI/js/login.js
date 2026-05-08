async function try_login(event) {
  if (event && event.preventDefault) event.preventDefault();
  const passkey_field = document.getElementById("passkey");
  const result = document.getElementById("set_login_result");
  if (!passkey_field) return;
  try {
    const resp = await post_json("/login", passkey_field.value);
    if (resp.err) {
      alert_class_switch(result, "fail");
      result.innerText = "Error: " + resp.err;
      return;
    }
    window.location.href = "/static/home.html";
  } catch (err) {
    alert_class_switch(result, "fail");
    result.innerText = "could not login, invalid response";
    console.log("could not login:\n" + err);
  }
}

function bind_login_form() {
  const form = document.getElementById("loginForm");
  if (form && !form.dataset.bound) {
    form.dataset.bound = "1";
    form.addEventListener("submit", try_login);
  }
  // Belt-and-suspenders: ensure Enter inside the password field always submits,
  // even if some browser/extension swallows the natural form-submit on Enter.
  const passkey_field = document.getElementById("passkey");
  if (passkey_field && !passkey_field.dataset.enterBound) {
    passkey_field.dataset.enterBound = "1";
    passkey_field.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        try_login(e);
      }
    });
  }
}

// Script tag uses `defer`, so the DOM is parsed before this runs and the
// form element is available immediately.  Cover the rare case the script
// is somehow loaded before parsing completes by also listening for
// DOMContentLoaded.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bind_login_form);
} else {
  bind_login_form();
}
