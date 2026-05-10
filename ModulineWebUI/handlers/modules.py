import json
import logging
import os
import threading
import time
import urllib.request
from urllib.error import URLError

logger = logging.getLogger(__name__)

MODULES_JSON_PATH = "/lib/firmware/gocontroll/modules.json"
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

# Shared enum lists used in MODULE_SCHEMAS.
_FREQ_6CH   = ["100Hz", "200Hz", "500Hz", "1kHz", "2kHz", "5kHz", "10kHz"]
_FUNC_INPUT = [
    "12bit_adc", "mv_analog", "digital_in",
    "frequency", "duty_low", "duty_high", "rpm", "pulse_counter",
]
_FUNC_ANALOG   = ["12bit_adc", "mv_analog"]
_FUNC_FREQ_DEP = ["frequency", "duty_low", "duty_high", "rpm", "pulse_counter"]

# Display labels — kept in sync with node-red-gocontroll/nodes/modules/*.html so
# the same option text appears in both the Web UI and Node-RED.
_FUNC_INPUT_LABELS = {
    "12bit_adc":     "Analog input - decimal (12 bit resolution)",
    "mv_analog":     "Analog input - mV (1mV resolution)",
    "digital_in":    "Digital input - status (high or low)",
    "frequency":     "Digital input - frequency (1Hz to 10 kHz)",
    "duty_low":      "Digital input - Duty cycle low time (0.1% resolution)",
    "duty_high":     "Digital input - Duty cycle high time (0.1% resolution)",
    "rpm":           "Digital input - Rotation speed (rps)",
    "pulse_counter": "Digital input - Pulse counter (paired channel)",
}
_FUNC_OUTPUT_6CH_LABELS = {
    "disabled":       "Output channel disabled",
    "halfbridge":     "Half bridge duty cycle controlled 0 – 100% (0-1000)",
    "lowside_duty":   "Low side switch duty cycle controlled 0 – 100% (0-1000)",
    "highside_duty":  "High side switch duty cycle controlled 0 – 100% (0-1000)",
    "lowside_bool":   "Low side switch on – off",
    "highside_bool":  "High side switch on – off",
    "peak_and_hold":  "Peak and hold current mode (half bridge)",
    "frequency_out":  "Frequency output 0 - 500 Hz (0-500)",
}
_FUNC_OUTPUT_10CH_LABELS = {
    "disabled":      "Output channel disabled",
    "highside_duty": "High side switch duty cycle controlled 0 – 100% (0-1000)",
    "highside_bool": "High side switch on – off",
}
_FUNC_BRIDGE_LABELS = {
    "disabled":      "Output channel disabled",
    "halfbridge":    "Half bridge duty cycle controlled 0 – 100% (0-1000)",
    "lowside_duty":  "Low side switch duty cycle controlled 0 – 100% (0-1000)",
    "highside_duty": "High side switch duty cycle controlled 0 – 100% (0-1000)",
    "lowside_bool":  "Low side switch on – off",
    "highside_bool": "High side switch on – off",
}
_VOLTAGE_RANGE_LABELS = {"5V": "0 - 5 volt", "12V": "0 - 12 volt", "24V": "0 - 24 volt"}
# Pull-up / pull-down label tables.  Texts match Node-RED exactly, including
# the 6-channel module's "3,2 kilo-ohm" labeling (which differs from the
# 10-channel module's "3,3 kilo-ohm" — Node-RED inconsistency, kept for parity).
_PULL_UP_LABELS_6CH   = {"none": "No pull up",   "3_3k": "3,2 kilo-ohm", "4_7k": "4,7 kilo-ohm", "10k": "10 kilo-ohm"}
_PULL_DOWN_LABELS_6CH = {"none": "No pull down", "3_3k": "3,2 kilo-ohm", "4_7k": "4,7 kilo-ohm", "10k": "10 kilo-ohm"}
_PULL_UP_LABELS_10CH  = {"none": "No pull up",   "10k":  "10 kilo-ohm"}
_PULL_DOWN_LABELS_10CH = {"none": "No pull down", "3_3k": "3,3 kilo-ohm"}
_FREQ_LABELS = {
    "100Hz": "100 Hz", "200Hz": "200 Hz", "500Hz": "500 Hz",
    "1kHz":  "1 kHz",  "2kHz":  "2 kHz",  "5kHz":  "5 kHz", "10kHz": "10 kHz",
}
_SENSOR_SUPPLY_LABELS = {"off": "Sensor supply disabled", "on": "Sensor supply enabled"}

# Editable-field schema per module_type.  The JS uses this to build the config UI.
# Structure:
#   channel_count  — number of channels
#   module_fields  — dict of module-level (non-per-channel) fields
#   channel_fields — list of per-channel field specs, in display order
#
# Field spec keys:
#   key          — JSON key name
#   type         — "enum" | "int" | "freq_pairs" | "bool_array"
#   values       — allowed values (enum / freq_pairs)
#   value_labels — optional dict mapping value -> display label
#   default      — safe default value
#   label        — human-readable column/row label
#   unit         — optional display unit string (int fields)
#   when_func    — list of func values for which this field is relevant (int fields)
#   hidden       — if True, the field is not rendered in the UI but its current
#                  value is preserved on save (allows JSON to keep fields the
#                  scanner/integrator wrote without exposing them as editable)
#   length       — array length (freq_pairs / bool_array)
#   pair_labels  — per-pair labels (freq_pairs)
MODULE_SCHEMAS: "dict[str, dict]" = {
    "input-6ch": {
        "channel_count": 6,
        "module_fields": {
            "sensor_supply_1": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 1"},
            "sensor_supply_2": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 2"},
            "sensor_supply_3": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 3"},
        },
        "channel_fields": [
            {"key": "name",                  "type": "string", "default": "",                            "label": "Name", "max_length": 32, "placeholder": "alias"},
            {"key": "func",                  "type": "enum", "values": _FUNC_INPUT,                     "value_labels": _FUNC_INPUT_LABELS,    "default": "12bit_adc", "label": "Function"},
            {"key": "voltage_range",         "type": "enum", "values": ["5V", "12V", "24V"],            "value_labels": _VOLTAGE_RANGE_LABELS, "default": "5V",       "label": "Voltage Range"},
            {"key": "pull_up",               "type": "enum", "values": ["none", "3_3k", "4_7k", "10k"], "value_labels": _PULL_UP_LABELS_6CH,   "default": "none",     "label": "Pull Up"},
            {"key": "pull_down",             "type": "enum", "values": ["none", "3_3k", "4_7k", "10k"], "value_labels": _PULL_DOWN_LABELS_6CH, "default": "none",     "label": "Pull Down"},
            {"key": "analog_filter_samples", "type": "int",  "min": 0, "max": 1000, "default": 0,       "label": "Filter Samples", "when_func": _FUNC_ANALOG,   "hidden": True},
            {"key": "pulses_per_rotation",   "type": "int",  "min": 0, "max": 200,  "default": 0,       "label": "PPR",            "when_func": _FUNC_FREQ_DEP, "hidden": True},
        ],
    },
    "input-10ch": {
        "channel_count": 10,
        "module_fields": {
            "sensor_supply_1": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 1"},
            "sensor_supply_2": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 2"},
        },
        "channel_fields": [
            {"key": "name",      "type": "string", "default": "",                       "label": "Name", "max_length": 32, "placeholder": "alias"},
            {"key": "func",      "type": "enum", "values": _FUNC_INPUT,     "value_labels": _FUNC_INPUT_LABELS,     "default": "12bit_adc", "label": "Function"},
            {"key": "pull_up",   "type": "enum", "values": ["none", "10k"], "value_labels": _PULL_UP_LABELS_10CH,   "default": "none",     "label": "Pull Up"},
            {"key": "pull_down", "type": "enum", "values": ["none", "3_3k"],"value_labels": _PULL_DOWN_LABELS_10CH, "default": "none",     "label": "Pull Down"},
        ],
    },
    "output-6ch": {
        "channel_count": 6,
        "module_fields": {
            "frequency_pairs": {
                "type": "freq_pairs",
                "length": 3,
                "values": _FREQ_6CH,
                "value_labels": _FREQ_LABELS,
                "default": ["100Hz", "100Hz", "100Hz"],
                "pair_labels": ["Channels 1+2", "Channels 3+4", "Channels 5+6"],
                "label": "PWM Frequency Pairs",
            },
        },
        "channel_fields": [
            {"key": "name",              "type": "string", "default": "",                              "label": "Name", "max_length": 32, "placeholder": "alias"},
            {"key": "func",              "type": "enum", "values": ["disabled", "halfbridge", "lowside_duty", "highside_duty", "lowside_bool", "highside_bool", "peak_and_hold", "frequency_out"], "value_labels": _FUNC_OUTPUT_6CH_LABELS, "default": "disabled", "label": "Function"},
            {"key": "current_max",       "type": "int",  "min": 0, "max": 4000,  "default": 4000, "label": "Max Current",  "unit": "mA"},
            {"key": "peak_current",      "type": "int",  "min": 0, "max": 3500,  "default": 1200, "label": "Peak Current", "unit": "mA", "when_func": ["peak_and_hold"]},
            {"key": "peak_time",         "type": "int",  "min": 0, "max": 65535, "default": 1500, "label": "Peak Time",    "unit": "µs", "when_func": ["peak_and_hold"]},
            {"key": "fast_loop_module",  "type": "int",  "min": 0, "max": 8,     "default": 0,    "label": "Fast Loop Module",  "hidden": True},
            {"key": "fast_loop_channel", "type": "int",  "min": 0, "max": 9,     "default": 0,    "label": "Fast Loop Channel", "hidden": True},
        ],
    },
    "output-10ch": {
        "channel_count": 10,
        "module_fields": {
            "frequency_pairs": {
                "type": "freq_pairs",
                "length": 5,
                "values": ["100Hz", "200Hz"],
                "value_labels": _FREQ_LABELS,
                "default": ["100Hz", "100Hz", "100Hz", "100Hz", "100Hz"],
                "pair_labels": ["Channels 1+2", "Channels 3+4", "Channels 5+6", "Channels 7+8", "Channels 9+10"],
                "label": "PWM Frequency Pairs",
            },
        },
        "channel_fields": [
            {"key": "name", "type": "string", "default": "", "label": "Name", "max_length": 32, "placeholder": "alias"},
            {"key": "func", "type": "enum", "values": ["disabled", "highside_duty", "highside_bool"], "value_labels": _FUNC_OUTPUT_10CH_LABELS, "default": "disabled", "label": "Function"},
        ],
    },
    "bridge-2ch": {
        "channel_count": 2,
        "module_fields": {},
        "channel_fields": [
            {"key": "name", "type": "string", "default": "", "label": "Name", "max_length": 32, "placeholder": "alias"},
            {"key": "func", "type": "enum", "values": ["disabled", "halfbridge", "lowside_duty", "highside_duty", "lowside_bool", "highside_bool"], "value_labels": _FUNC_BRIDGE_LABELS, "default": "disabled", "label": "Function"},
            {"key": "freq", "type": "enum", "values": _FREQ_6CH, "value_labels": _FREQ_LABELS, "default": "100Hz", "label": "Frequency"},
        ],
    },
    "input-4-20ma": {
        "channel_count": 10,
        "module_fields": {
            # 5 onafhankelijke supply-rails — schema gelijk aan input-6ch/10ch
            # voor consistente UX. Bron: input-4-20ma.md §3 (architectuur-doc).
            "sensor_supply_1": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 1"},
            "sensor_supply_2": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 2"},
            "sensor_supply_3": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 3"},
            "sensor_supply_4": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 4"},
            "sensor_supply_5": {"type": "enum", "values": ["off", "on"], "value_labels": _SENSOR_SUPPLY_LABELS, "default": "off", "label": "Sensor Supply 5"},
        },
        "channel_fields": [
            {"key": "name", "type": "string", "default": "", "label": "Name", "max_length": 32, "placeholder": "alias"},
            # Op de 4-20 mA module is er geen `func`-keuze (alle ingangen
            # zijn altijd actief op hardware-niveau, zie input-4-20ma.md §4).
            # Niets om te tonen in de UI dus.
        ],
    },
}

# Keys written by the scanner that must never be overwritten by the config editor.
# `firmware` (raw scan string), `manufacturer`, `qr_front`, `qr_back` are physical
# identification metadata produced by go-modules and are immutable from the UI's
# point of view.
READ_ONLY_SLOT_KEYS = frozenset({
    "slot", "module_type", "article_number", "hardware_version", "firmware_version",
    "firmware", "manufacturer", "qr_front", "qr_back",
})

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


def _load_modules_json() -> "tuple[list, bool]":
    """Return (slots_list, is_new_format).  New format has a top-level 'slots' key."""
    with open(MODULES_JSON_PATH, "r") as fh:
        raw = json.load(fh)
    if isinstance(raw, dict) and "slots" in raw:
        return raw.get("slots", []), True
    return (raw if isinstance(raw, list) else []), False


def _parse_slots_new_format(slots: list) -> list:
    out = []
    for entry in slots:
        slot = entry.get("slot")
        article_number = entry.get("article_number")
        article = str(article_number) if article_number else ""
        type_code = article[:6] if len(article) >= 6 else ""
        fw_ver = entry.get("firmware_version", "")
        hw_ver = entry.get("hardware_version", "")
        recognised = bool(type_code) and bool(fw_ver)
        out.append({
            "slot": slot,
            "module_type": entry.get("module_type", ""),
            "manufacturer": entry.get("manufacturer", 0),
            "qr_front": entry.get("qr_front", 0),
            "qr_back": entry.get("qr_back", 0),
            "raw_firmware": entry.get("firmware", ""),
            "empty": False,
            "recognised": recognised,
            "article": article,
            "module_type_code": type_code,
            "module_name": MODULE_TYPE_NAMES.get(type_code, "Unknown module") if recognised else "",
            "hardware_version": hw_ver,
            "firmware_version": fw_ver,
        })
    return out


def _parse_slots_old_format(slots: list) -> list:
    out = []
    for entry in slots:
        slot = entry.get("slot")
        fw = entry.get("firmware", "")
        common = {
            "slot": slot,
            "module_type": "",
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


def get_modules() -> list:
    """Read modules.json and return one entry per slot, enriched with decoded fields."""
    slots, new_fmt = _load_modules_json()
    return _parse_slots_new_format(slots) if new_fmt else _parse_slots_old_format(slots)


def get_module_config(slot: int) -> dict:
    """Return editable configuration for one slot plus its schema.

    Raises ValueError when the slot is not found or the file uses the old format.
    Raises FileNotFoundError when modules.json is absent.
    """
    slots, new_fmt = _load_modules_json()
    if not new_fmt:
        raise ValueError("Module configuration editing requires the new modules.json format")

    for entry in slots:
        if entry.get("slot") == slot:
            module_type = entry.get("module_type", "")
            schema = MODULE_SCHEMAS.get(module_type)

            # Normalise channels: fill gaps with schema defaults.
            channels: list = []
            if schema:
                ch_count = schema["channel_count"]
                existing = {ch["channel"]: ch for ch in entry.get("channels", [])}
                ch_defaults = {f["key"]: f["default"] for f in schema["channel_fields"]}
                for i in range(1, ch_count + 1):
                    channels.append(dict(existing[i]) if i in existing else {"channel": i, **ch_defaults})
            else:
                channels = [dict(c) for c in entry.get("channels", [])]

            # Normalise module-level fields: add schema defaults for missing keys.
            module_data = dict(entry.get("module", {}))
            if schema:
                for key, spec in schema.get("module_fields", {}).items():
                    if key not in module_data:
                        module_data[key] = spec.get("default")

            return {
                "slot": slot,
                "module_type": module_type,
                "label": entry.get("label", ""),
                "module": module_data,
                "channels": channels,
                "schema": schema,
            }

    raise ValueError(f"Slot {slot} not found in modules.json")


def save_module_config(slot: int, payload: dict) -> None:
    """Write editable fields for a slot back to modules.json atomically.

    READ_ONLY_SLOT_KEYS are silently skipped so the scanner-written fields
    are never overwritten.
    """
    with open(MODULES_JSON_PATH, "r") as fh:
        data = json.load(fh)

    if not (isinstance(data, dict) and "slots" in data):
        raise ValueError("Module configuration editing requires the new modules.json format")

    for entry in data["slots"]:
        if entry.get("slot") == slot:
            for key, val in payload.items():
                if key not in READ_ONLY_SLOT_KEYS:
                    entry[key] = val
            break
    else:
        raise ValueError(f"Slot {slot} not found in modules.json")

    tmp = MODULES_JSON_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, MODULES_JSON_PATH)


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
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "go-web-ui"})
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
