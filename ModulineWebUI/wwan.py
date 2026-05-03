import json
import subprocess

from microdot import Request
from microdot.session import Session, with_session

from ModulineWebUI.app import app, auth
from ModulineWebUI.handlers.service import get_service, set_service


@app.get("/api/get_wwan")
@with_session
@auth
async def get_wwan(req: Request, session: Session):
    return json.dumps({"state": get_service("go-wwan")})


@app.post("/api/set_wwan")
@with_session
@auth
async def set_wwan(req: Request, session: Session):
    new_state = req.json["new_state"]
    is_changed, error = set_service("go-wwan", new_state)
    if is_changed:
        return json.dumps({"new_state": new_state})
    else:
        return json.dumps({"err": f"Failed to change go-wwan state {error}"})


def get_sim_num() -> dict:
    pass


def _clean(v):
    """ModemManager uses '--' as the absent-value sentinel; map that to ''."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s == "--" else s


@app.get("/api/get_wwan_stats")
@with_session
@auth
async def get_wwan_stats(req: Request, session: Session):
    try:
        ml = subprocess.run(
            ["mmcli", "-J", "--list-modems"], stdout=subprocess.PIPE, text=True,
        )
        ml.check_returncode()
        modems = json.loads(ml.stdout).get("modem-list", [])
        if not modems:
            return json.dumps({"err": "No modem detected"})
        modem_path = modems[0]

        mout = subprocess.run(
            ["mmcli", "-J", "--modem=" + modem_path],
            stdout=subprocess.PIPE, text=True,
        )
        mout.check_returncode()
        m = json.loads(mout.stdout)["modem"]
        gen = m.get("generic", {}) or {}
        three = m.get("3gpp", {}) or {}

        sq = gen.get("signal-quality", {}) or {}
        access_techs = gen.get("access-technologies", []) or []

        stats = {
            "model":              _clean(gen.get("model")),
            "manufacturer":       _clean(gen.get("manufacturer")),
            "state":              _clean(gen.get("state")),
            "access_tech":        ", ".join(t.upper() for t in access_techs) if access_techs else "",
            "signal":             _clean(sq.get("value") if isinstance(sq, dict) else sq),
            "imei":               _clean(three.get("imei")),
            "operator":           _clean(three.get("operator-name")),
            "operator_code":      _clean(three.get("operator-code")),
            "registration_state": _clean(three.get("registration-state")),
            # SIM fields populated below
            "iccid": "",
            "imsi": "",
            "sim_operator": "",
            # Bearer fields populated below
            "apn": "",
            "ip": "",
            "gateway": "",
            "dns": "",
        }

        # SIM info — by index (last segment of the SIM path)
        sim_path = _clean(gen.get("sim"))
        if sim_path:
            try:
                sout = subprocess.run(
                    ["mmcli", "-J", "-i", sim_path],
                    stdout=subprocess.PIPE, text=True,
                )
                sout.check_returncode()
                sprops = json.loads(sout.stdout).get("sim", {}).get("properties", {}) or {}
                stats["iccid"]        = _clean(sprops.get("iccid"))
                stats["imsi"]         = _clean(sprops.get("imsi"))
                stats["sim_operator"] = _clean(sprops.get("operator-name"))
            except Exception:
                pass

        # Bearer info — APN, IPv4 address, gateway, DNS
        bearers = gen.get("bearers", []) or []
        if bearers:
            try:
                bout = subprocess.run(
                    ["mmcli", "-J", "-b", bearers[0]],
                    stdout=subprocess.PIPE, text=True,
                )
                bout.check_returncode()
                b = json.loads(bout.stdout).get("bearer", {}) or {}
                bprops = b.get("properties", {}) or {}
                stats["apn"] = _clean(bprops.get("apn"))
                v4 = b.get("ipv4-config", {}) or {}
                stats["ip"]      = _clean(v4.get("address"))
                stats["gateway"] = _clean(v4.get("gateway"))
                dns_list = v4.get("dns", []) or []
                stats["dns"] = ", ".join(d for d in dns_list if d and d != "--")
            except Exception:
                pass

        # Fallback APN from NetworkManager profile if bearer didn't carry one
        if not stats["apn"]:
            try:
                aout = subprocess.run(
                    ["nmcli", "-t", "-f", "gsm.apn", "con", "show", "GO-cellular"],
                    stdout=subprocess.PIPE, text=True,
                )
                if aout.returncode == 0:
                    for line in aout.stdout.strip().split("\n"):
                        if line.startswith("gsm.apn:"):
                            stats["apn"] = _clean(line.split(":", 1)[1])
                            break
            except Exception:
                pass

        return json.dumps(stats)
    except Exception as ex:
        return json.dumps({"err": f"Could not get modem information: {ex}"})


def get_apn() -> dict:
    pass


def set_apn(apn: dict):
    pass


def set_pin(pin: dict):
    pass
