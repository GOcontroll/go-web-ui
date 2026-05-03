async function set_wwan() {
    //get what the next state of wwan should be
    let set_state = {};
    const cb = document.getElementById("wwan");
    //current state of checked is after it was clicked, so the state it needs to become
    set_state.new_state = cb.checked;
    //try to make it a reality
    try {
        const resp = await post_json("/api/set_wwan", set_state);
        if (resp.err != undefined) {
            //server failed to toggle wwan
            cb.checked = !cb.checked;
            console.log("Could not toggle wwan:\n" + resp.err);
        }
    } catch (err) {
        console.log("Could not toggle wwan:\n" + err);
        cb.checked = !cb.checked;
    }
}

function setText(id, value, fallback) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = (value === undefined || value === null || value === "") ? (fallback || "—") : value;
}

function fmtSignal(s) {
    if (s === undefined || s === null || s === "") return "—";
    return s + " %";
}

async function refreshWwanStats() {
    try {
        const stats = await (await fetch('/api/get_wwan_stats')).json();
        if (stats.err) {
            console.log(stats.err);
            const body = document.getElementsByClassName("body")[0];
            if (body && !body.querySelector(".alert-box.info")) {
                const note = document.createElement("p");
                note.className = "alert-box info";
                note.style.marginTop = "10px";
                note.textContent = "Could not get modem info. If the modem was just switched on, this can take some time to be available.";
                body.appendChild(note);
            }
            return;
        }
        // Modem
        setText("manufacturer", stats.manufacturer);
        setText("model",        stats.model);
        setText("imei",         stats.imei);
        setText("modem_state",  stats.state);
        // Network
        setText("operator",           stats.operator);
        setText("operator_code",      stats.operator_code);
        setText("registration_state", stats.registration_state);
        setText("signal",             fmtSignal(stats.signal));
        // SIM
        setText("iccid",        stats.iccid);
        setText("imsi",         stats.imsi);
        setText("sim_operator", stats.sim_operator);
        // Connection / bearer
        setText("apn",              stats.apn);
        setText("cellular_ip",      stats.ip);
        setText("cellular_gateway", stats.gateway);
        setText("cellular_dns",     stats.dns);
        // Reveal cards
        document.getElementById("wwan_info").style.display    = "";
        document.getElementById("network_info").style.display = "";
        // Show SIM card only if we got at least an ICCID or IMSI
        document.getElementById("sim_info").style.display = (stats.iccid || stats.imsi) ? "" : "none";
        // Show connection card only if APN or IP is known
        document.getElementById("bearer_info").style.display = (stats.apn || stats.ip) ? "" : "none";
    } catch (err) {
        console.log(err);
    }
}

document.addEventListener('DOMContentLoaded', async function () {
    try {
        const wwan_request = await (await fetch('/api/get_wwan')).json();
        document.getElementById("wwan").checked = !!wwan_request.state;
        if (wwan_request.state) {
            await refreshWwanStats();
            // Refresh signal/IP/state every 10s while page is open
            setInterval(refreshWwanStats, 10000);
        }
    } catch (err) {
        console.log(err);
    }
}, false);
