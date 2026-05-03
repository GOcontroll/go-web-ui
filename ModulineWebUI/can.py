import json
import os
import subprocess
import time

from microdot import Request
from microdot.session import Session, with_session

from ModulineWebUI.app import app, auth


# Module-global state for busload computation. {ifc: {"t": monotonic, "p": packets, "b": bytes}}
_load_state: dict = {}

# Bitrate cache for busload calc. {ifc: (cached_at_monotonic, bitrate_bps)}
_bitrate_cache: dict = {}
_BITRATE_TTL = 30.0


def _read_int(path: str) -> int:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def _bus_counters(ifc: str) -> tuple:
    base = f"/sys/class/net/{ifc}/statistics"
    p = _read_int(f"{base}/rx_packets") + _read_int(f"{base}/tx_packets")
    b = _read_int(f"{base}/rx_bytes") + _read_int(f"{base}/tx_bytes")
    return p, b


def _go_can_run(*args, json_out: bool = False):
    """Invoke go-can. Raises on non-zero exit. Returns parsed JSON when json_out=True."""
    cmd = ["go-can"]
    if json_out:
        cmd.append("--json")
    cmd.extend(args)
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    if res.returncode != 0:
        msg = res.stderr.strip() or res.stdout.strip() or f"exit {res.returncode}"
        raise RuntimeError(f"go-can {' '.join(args)}: {msg}")
    if json_out:
        return json.loads(res.stdout)
    return res.stdout


def _go_can_json(*args):
    return _go_can_run(*args, json_out=True)


def _ip_link_bitrate(ifc: str) -> int:
    try:
        res = subprocess.run(
            ["ip", "-j", "-d", "link", "show", ifc],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode != 0:
            return 0
        data = json.loads(res.stdout)
        return int(data[0]["linkinfo"]["info_data"]["bittiming"]["bitrate"])
    except Exception:
        return 0


def _bitrate_for(ifc: str) -> int:
    now = time.monotonic()
    cached = _bitrate_cache.get(ifc)
    if cached and (now - cached[0]) < _BITRATE_TTL:
        return cached[1]
    bitrate = _ip_link_bitrate(ifc)
    _bitrate_cache[ifc] = (now, bitrate)
    return bitrate


def _list_can_ifaces() -> list:
    try:
        return sorted(
            ifc for ifc in os.listdir("/sys/class/net")
            if ifc.startswith("can") and os.path.isdir(f"/sys/class/net/{ifc}/statistics")
        )
    except Exception:
        return []


@app.get("/api/get_can_list")
@with_session
@auth
async def get_can_list(req: Request, session: Session):
    try:
        info = _go_can_json("list")
        out = {
            "baseboard": info.get("baseboard", "unknown"),
            "interfaces": [],
        }
        for entry in info.get("interfaces", []):
            name = entry.get("name", "")
            row = {
                "name": name,
                "present": entry.get("present", False),
                "up": entry.get("up", False),
                "bitrate": None,
                "state": "absent",
            }
            if row["present"]:
                try:
                    show = _go_can_json("show", name)
                    row["bitrate"] = show.get("config", {}).get("bitrate")
                    row["state"] = show.get("live", {}).get("state", "unknown")
                    if row["bitrate"]:
                        _bitrate_cache[name] = (time.monotonic(), int(row["bitrate"]))
                except Exception as ex:
                    row["err"] = str(ex)
            out["interfaces"].append(row)
        return json.dumps(out)
    except Exception as ex:
        return json.dumps({"err": f"Could not list CAN interfaces\n{ex}"})


@app.post("/api/set_can_bitrate")
@with_session
@auth
async def set_can_bitrate(req: Request, session: Session):
    data = req.json or {}
    name = str(data.get("name", ""))
    bitrate_in = data.get("bitrate")
    if not name.startswith("can") or not name[3:].isdigit():
        return json.dumps({"err": f"Invalid interface name: {name}"})
    try:
        bitrate = int(bitrate_in)
    except (TypeError, ValueError):
        return json.dumps({"err": "bitrate must be an integer (bit/s)"})
    if bitrate < 1000 or bitrate > 8_000_000:
        return json.dumps({"err": "bitrate out of range (1k..8M bit/s)"})
    try:
        _go_can_run("set", name, "bitrate", str(bitrate))
        _bitrate_cache[name] = (time.monotonic(), bitrate)
        return json.dumps({"name": name, "bitrate": bitrate})
    except Exception as ex:
        return json.dumps({"err": f"Could not set bitrate\n{ex}"})


@app.get("/api/get_can_load")
@with_session
@auth
async def get_can_load(req: Request, session: Session):
    """Per-bus busload percentage based on /sys statistics deltas vs previous call.
    First call after the server (re)starts seeds the state and returns 0% for that bus."""
    out = {}
    now = time.monotonic()
    for ifc in _list_can_ifaces():
        p, b = _bus_counters(ifc)
        prev = _load_state.get(ifc)
        load_pct = 0.0
        if prev is not None:
            dt = now - prev["t"]
            dp = max(0, p - prev["p"])
            db = max(0, b - prev["b"])
            if dt > 0:
                # Approximation: ~47 bits per CAN classic frame overhead + 8 bits per data byte.
                # Bitstuffing (~0..20%) is ignored, so true load is slightly higher.
                bits = dp * 47 + db * 8
                bitrate = _bitrate_for(ifc)
                if bitrate > 0:
                    load_pct = (bits / dt) / bitrate * 100.0
                    if load_pct < 0:
                        load_pct = 0.0
                    elif load_pct > 100:
                        load_pct = 100.0
        _load_state[ifc] = {"t": now, "p": p, "b": b}
        out[ifc] = round(load_pct, 1)
    return json.dumps(out)
