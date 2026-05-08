//If this list is changed also change it in controller.py
const services_list = [
  ["ssh", "SSH", "OpenSSH service, to login over a network"],
  ["go-simulink", "Simulink", "Used to automatically start a simulink model"],
  ["nodered", "NodeRED", "The NodeRED programming interface"],
  [
    "go-bluetooth",
    "Bluetooth server",
    "The bluetooth server that is used with the GOcontroll Configuration app",
  ],
  [
    "go-upload-server",
    "Simulink upload server",
    "A server that accepts new simulink models to be uploaded",
  ],
  [
    "go-auto-shutdown",
    "Auto shutdown",
    "Auto shutdown when there is no kl15 and simulink is not running",
  ],
  ["gadget-getty@ttyGS0", "USB terminal", "Log in through the USB interface"],
  ["getty@ttymxc2", "Serial terminal", "Log in through the rs232 interface"],
  [
    "go-web-ui",
    "Web UI",
    "The service that runs this web interface. Disabling it will make this UI unreachable.",
  ],
];

function confirmDisableWebUi() {
  return new Promise((resolve) => {
    let resolved = false;
    const safe = (v) => { if (!resolved) { resolved = true; resolve(v); } };
    const overlay = showModal({
      title: "Disable Web UI service?",
      variant: "danger",
      body: `<p>This is the service that runs <strong>this</strong> Web UI.</p>
             <p>Disabling it will <strong>break access to this interface</strong>.
                You will need another way (SSH, USB or serial terminal) to start it again.</p>
             <p>Are you sure you want to continue?</p>`,
      actions: [
        { label: "Cancel",  onClick: () => safe(false) },
        { label: "Disable", primary: true, danger: true, onClick: () => safe(true) },
      ],
    });
    const obs = new MutationObserver(() => {
      if (!overlay.parentNode) { obs.disconnect(); safe(false); }
    });
    obs.observe(document.body, { childList: true });
  });
}

async function set_service(service) {
  //get what the next state of wifi should be
  let set_state = {};
  let cb = document.getElementById("service" + service);
  //current state of checked is after it was clicked, so the state it needs to become
  set_state.new_state = cb.checked;
  set_state.service = services_list[service][0];
  // Confirm before disabling the Web UI service itself, since that breaks access to this UI.
  if (set_state.service === "go-web-ui" && !set_state.new_state) {
    if (!(await confirmDisableWebUi())) {
      cb.checked = true;
      return;
    }
  }
  //try to make it a reality
  try {
    const resp = await post_json("/api/set_service", set_state);
    if (resp.err != undefined) {
      //server failed to toggle wifi
      cb.checked = !set_state.new_state;
      alert("Could not toggle " + services_list[service][0] + ":\n" + resp.err);
    } else {
      cb.checked = resp.new_state;
    }
  } catch (err) {
    alert("Could not toggle " + services_list[service][0] + ":\n" + err);
    cb.checked = !set_state.new_state;
  }
}

async function get_service(service, index) {
  try {
    const promise = post_json("/api/get_service", service[0]);
    const service_templ = document.getElementById("service");

    const new_service = service_templ.content.cloneNode(true);
    let p = new_service.querySelector("p");
    p.textContent = service[1];
    let tooltip = new_service.querySelector(".tooltiptext");
    tooltip.textContent = service[2];
    let cb = new_service.querySelector("input");
    cb.id = "service" + index;
    cb.setAttribute("onclick", "set_service(" + index + ")");
    const resp = await promise;
    if (resp.err) {
      console.log("Could not get the state of " + service[0] + ":\n" + resp.err);
      return;
    }
    cb.checked = resp.state;
    return new_service;
  } catch (err) {
    console.log("Could not get the state of " + service[0] + ":\n" + err);
  }
}

document.addEventListener(
  "DOMContentLoaded",
  async function () {
    const services = document.getElementById("services");
    services.textContent = "";
    var promises = [];
    for (var i = 0; i < services_list.length; i++) {
      promises.push(get_service(services_list[i], i));
    }
    for (const promise of promises) {
      const child = await promise
      if (child) {
        services.appendChild(child);
      }
    }
  },
  false
);
