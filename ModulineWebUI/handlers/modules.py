import json
import logging
import os
import threading
import time
import urllib.request
from urllib.error import URLError

logger = logging.getLogger(__name__)

MODULES_JSON_PATH = "/usr/lib/firmware/gocontroll/modules.json"
PLATFORM_PATH = "/sys/firmware/devicetree/base/platform"
PINNING_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "module_pinning.json",
)
CONTROLLER_PINNING_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "controller_pinning.json",
)
MANIFEST_URL = "https://firmware.gocontroll.com/modules/manifest.json"
MANIFEST_CACHE_TTL = 300  # seconds
MANIFEST_TIMEOUT = 5

# Module type code (first 6 digits of the 8-digit article number) to human-readable name.
# Source of truth: GOcontroll-Architecture/modules/naming.md
MODULE_TYPE_NAMES = {
    "201001": "6 Channel Input Module",
    "201002": "10 Channel Input Module",
    "201003": "4-20 mA Input Module",
    "201004": "RTD Input Module",
    "201005": "Loadcell Input Module",
    "202001": "2 Channel Power Bridge Module",
    "202002": "6 Channel Output Module",
    "202003": "10 Channel Output Module",
    "203003": "Anleg IR Module",
    "203004": "Multibus",
}

_manifest_cache = {"data": None, "ts": 0.0}
_manifest_lock = threading.Lock()


def decode_firmware_string(fw_str: str):
    """
    Decode a modules.json firmware string like '20-20-2-6-2-2-0'.

    Layout AA-BB-C-D-E-F-G:
      article = AA + BB + zero-pad(C,2) + zero-pad(D,2)   -> 8 digits, e.g. '20200206'
      hardware version = '1.' + zero-pad(D,2)             -> '1.06'
      firmware version = E.F.G                            -> '2.2.0'

    Returns None for empty or unparseable strings.
    """
    if not fw_str:
        return None
    parts = fw_str.split("-")
    if len(parts) != 7 or not all(p.isdigit() for p in parts):
        return None
    aa, bb, c, d, e, f, g = parts
    article = f"{aa}{bb}{c.zfill(2)}{d.zfill(2)}"
    if len(article) != 8:
        return None
    type_code = article[:6]
    hw_code = article[6:]
    return {
        "article": article,
        "module_type_code": type_code,
        "module_name": MODULE_TYPE_NAMES.get(type_code, "Unknown module"),
        "hardware_version": f"1.{hw_code}",
        "firmware_version": f"{e}.{f}.{g}",
    }


def get_modules() -> list:
    """Read modules.json and return one entry per slot, enriched with decoded fields."""
    with open(MODULES_JSON_PATH, "r") as f:
        raw = json.load(f)

    out = []
    for entry in raw:
        slot = entry.get("slot")
        fw = entry.get("firmware", "")
        common = {
            "slot": slot,
            "manufacturer": entry.get("manufacturer", 0),
            "qr_front": entry.get("qr_front", 0),
            "qr_back": entry.get("qr_back", 0),
            "raw_firmware": fw,
        }
        decoded = decode_firmware_string(fw)
        if decoded is None:
            out.append({**common, "empty": not bool(fw), "recognised": False})
        else:
            out.append({**common, "empty": False, "recognised": True, **decoded})
    return out


def fetch_manifest(force: bool = False):
    """
    Returns (manifest_dict | None, error_message | None).

    manifest_dict is keyed by 8-digit article id, each entry containing
    'name', 'hardware_version', 'latest_firmware'.
    Successful fetches are cached for MANIFEST_CACHE_TTL seconds.
    Failures are not cached; the caller can keep using the previous good result.
    """
    now = time.time()
    with _manifest_lock:
        data = _manifest_cache["data"]
        ts = _manifest_cache["ts"]
        if (not force) and data is not None and (now - ts) < MANIFEST_CACHE_TTL:
            return data, None

    try:
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "go-webui"})
        with urllib.request.urlopen(req, timeout=MANIFEST_TIMEOUT) as resp:
            payload = json.load(resp)
    except URLError as ex:
        logger.info("Manifest fetch failed (no internet?): %s", ex)
        return data, f"Manifest unreachable: {ex.reason if hasattr(ex, 'reason') else ex}"
    except Exception as ex:
        logger.error("Manifest fetch failed: %s", ex)
        return data, f"Manifest fetch failed: {ex}"

    by_article = {}
    for item in payload.get("modules", []):
        article = str(item.get("id", ""))
        if not article:
            continue
        by_article[article] = {
            "name": item.get("name", ""),
            "hardware_version": item.get("hardware_version", ""),
            "latest_firmware": item.get("latest_firmware", ""),
        }
    with _manifest_lock:
        _manifest_cache["data"] = by_article
        _manifest_cache["ts"] = now
    return by_article, None


# ----------------------------------------------------------------------------
# Pinning
# ----------------------------------------------------------------------------

_pinning_cache = None
_pinning_lock = threading.Lock()


def _load_pinning() -> dict:
    """Load module_pinning.json once and cache it in memory."""
    global _pinning_cache
    with _pinning_lock:
        if _pinning_cache is None:
            try:
                with open(PINNING_JSON_PATH, "r", encoding="utf-8") as f:
                    _pinning_cache = json.load(f)
            except Exception as ex:
                logger.error("Failed to load %s: %s", PINNING_JSON_PATH, ex)
                _pinning_cache = {}
        return _pinning_cache


def _read_platform() -> str:
    try:
        with open(PLATFORM_PATH, "r") as f:
            return f.read().strip("\x00 \t\n\r")
    except Exception:
        return ""


def get_slot_prefix() -> "tuple[str, str]":
    """
    Return (slot_prefix, platform_string).

    slot_prefix matches the column names used in pinning.md:
      - M4S  -> Moduline IV / V / L4 (8 slots)
      - MMS  -> Moduline M1 (4 slots)
      - MDS  -> Moduline HMI1 / Display (2 slots)
    Defaults to M4S when the platform string can't be classified.
    """
    plat = _read_platform()
    low = plat.lower()
    if "m1" in low or "mini" in low:
        return "MMS", plat
    if "hmi" in low or "display" in low:
        return "MDS", plat
    return "M4S", plat


# Map a slot label (M4S1..M4S8, MMS1..MMS4, MDS1..MDS2) to the connector image
# that physically carries that slot's pins. Source: pinning.md "Connector overzicht".
SLOT_CONNECTOR_IMAGE = {
    # Moduline L4/V — 26-pin connectors per pair of slots
    "M4S1": "/assets/modules/iv_con_a.png",
    "M4S2": "/assets/modules/iv_con_a.png",
    "M4S3": "/assets/modules/iv_con_b.png",
    "M4S4": "/assets/modules/iv_con_b.png",
    "M4S5": "/assets/modules/iv_con_d.png",
    "M4S6": "/assets/modules/iv_con_d.png",
    "M4S7": "/assets/modules/iv_con_e.png",
    "M4S8": "/assets/modules/iv_con_e.png",
    # Moduline M1 — 34-pin connectors
    "MMS1": "/assets/modules/mini_con_a.jpg",
    "MMS2": "/assets/modules/mini_con_a.jpg",
    "MMS3": "/assets/modules/mini_con_b.jpg",
    "MMS4": "/assets/modules/mini_con_b.jpg",
    # Moduline HMI1 — single connector overview
    "MDS1": "/assets/modules/display_overview.jpg",
    "MDS2": "/assets/modules/display_overview.jpg",
}

# Map slot prefix to the platform 3D overview image.
PLATFORM_IMAGE = {
    "M4S": "/assets/modules/iv_3d.png",
    "MMS": "/assets/modules/mini_3d.png",
    "MDS": "/assets/modules/display_3d.png",
}


_controller_pinning_cache = None
_controller_pinning_lock = threading.Lock()


def _load_controller_pinning() -> dict:
    global _controller_pinning_cache
    with _controller_pinning_lock:
        if _controller_pinning_cache is None:
            try:
                with open(CONTROLLER_PINNING_JSON_PATH, "r", encoding="utf-8") as f:
                    _controller_pinning_cache = json.load(f)
            except Exception as ex:
                logger.error("Failed to load %s: %s", CONTROLLER_PINNING_JSON_PATH, ex)
                _controller_pinning_cache = {}
        return _controller_pinning_cache


def get_controller_pinning():
    """Return the controller-level pin table for the current platform.

    Returns dict with platform/connector_label/description/connector_image/pins,
    or None when the platform is unrecognised.
    """
    prefix, platform = get_slot_prefix()
    data = _load_controller_pinning()
    info = data.get(prefix)
    if info is None:
        return None
    return {
        "platform": platform,
        "slot_prefix": prefix,
        "platforms": info.get("platforms", []),
        "connector_label": info.get("connector_label", ""),
        "description": info.get("description", ""),
        "connector_image": info.get("connector_image"),
        "platform_image": PLATFORM_IMAGE.get(prefix),
        "pins": info.get("pins", []),
    }


def get_pinning_for(type_code: str, slot: int):
    """Return per-pin info for a module type at a given controller slot.

    Returns None if the module type is unknown to the pinning data.
    Returns a dict with an empty 'pins' list and a 'note' if the slot label
    isn't part of the module's pinning table.
    """
    data = _load_pinning()
    module = data.get(type_code)
    if module is None:
        return None

    prefix, platform = get_slot_prefix()
    slot_label = f"{prefix}{slot}"

    connector_image = SLOT_CONNECTOR_IMAGE.get(slot_label)
    platform_image = PLATFORM_IMAGE.get(prefix)

    if slot_label not in module["slots"]:
        return {
            "module_name": module["name"],
            "type_code": type_code,
            "slot": slot,
            "slot_label": slot_label,
            "platform": platform,
            "platform_image": platform_image,
            "connector_image": connector_image,
            "pins": [],
            "note": f"No pinning defined for {slot_label}",
        }

    idx = module["slots"].index(slot_label)
    pins = []
    for pin_def in module["pins"]:
        pin_value = pin_def["pins"][idx] if idx < len(pin_def["pins"]) else ""
        pins.append({
            "function": pin_def["function"],
            "description": pin_def["description"],
            "pin": pin_value,
        })
    return {
        "module_name": module["name"],
        "type_code": type_code,
        "slot": slot,
        "slot_label": slot_label,
        "platform": platform,
        "platform_image": platform_image,
        "connector_image": connector_image,
        "pins": pins,
    }
