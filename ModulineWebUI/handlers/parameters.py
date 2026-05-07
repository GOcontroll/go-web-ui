"""
Application configuration & environment-parameter editor.

Source of truth lives at:
    /etc/gocontroll/config.json    application config (key -> string value)
    /etc/gocontroll/parameters.js  Node-RED env vars in module.exports form

On first read of a missing source-of-truth file, content is seeded from legacy
locations:
    /usr/moduline/application/config.json
    /usr/moduline/application/parameters.js
    /etc/go-simulink/*             each file is one key (filename) -> value (contents)

On save, the source of truth is written first; then values are mirrored back to
the legacy locations *if those legacy files already exist*. This keeps clients
that still read the old paths in sync without spuriously creating new files or
directories on systems that don't have them.
"""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("/etc/gocontroll")
CONFIG_PATH = CONFIG_DIR / "config.json"
PARAMS_PATH = CONFIG_DIR / "parameters.js"

LEGACY_APP_DIR = Path("/usr/moduline/application")
LEGACY_APP_CONFIG = LEGACY_APP_DIR / "config.json"
LEGACY_APP_PARAMS = LEGACY_APP_DIR / "parameters.js"
LEGACY_SIMULINK_DIR = Path("/etc/go-simulink")


# ----------------------------------------------------------------------------
# Atomic write helpers
# ----------------------------------------------------------------------------

def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_json(path: Path, data) -> None:
    _atomic_write_text(path, json.dumps(data, indent=4) + "\n")


def _stringify(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return str(v)


# ----------------------------------------------------------------------------
# config.json
# ----------------------------------------------------------------------------

def _migrate_config_if_needed() -> None:
    """Seed /etc/gocontroll/config.json from legacy locations on first run."""
    if CONFIG_PATH.exists():
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as ex:
        logger.error("Cannot create %s: %s", CONFIG_DIR, ex)
        raise

    seed: dict = {}
    if LEGACY_APP_CONFIG.exists():
        try:
            with open(LEGACY_APP_CONFIG, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    seed[str(k)] = _stringify(v)
        except Exception as ex:
            logger.warning("Could not read %s: %s", LEGACY_APP_CONFIG, ex)

    if LEGACY_SIMULINK_DIR.is_dir():
        try:
            for entry in sorted(LEGACY_SIMULINK_DIR.iterdir()):
                if entry.is_file():
                    try:
                        seed[entry.name] = entry.read_text(encoding="utf-8").strip()
                    except Exception as ex:
                        logger.warning("Skipped %s: %s", entry, ex)
        except Exception as ex:
            logger.warning("Could not enumerate %s: %s", LEGACY_SIMULINK_DIR, ex)

    _atomic_write_json(CONFIG_PATH, seed)
    logger.info("Seeded %s with %d keys", CONFIG_PATH, len(seed))


def get_config() -> dict:
    _migrate_config_if_needed()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): _stringify(v) for k, v in data.items()}


def save_config(data: dict) -> None:
    """Write config.json and mirror values to existing legacy locations."""
    _migrate_config_if_needed()
    cleaned = {str(k): _stringify(v) for k, v in (data or {}).items() if str(k).strip()}
    _atomic_write_json(CONFIG_PATH, cleaned)

    # Mirror to /usr/moduline/application/config.json if the legacy file exists.
    if LEGACY_APP_CONFIG.exists():
        try:
            _atomic_write_json(LEGACY_APP_CONFIG, cleaned)
        except Exception as ex:
            logger.warning("Could not mirror to %s: %s", LEGACY_APP_CONFIG, ex)

    # Mirror values back to /etc/go-simulink/<key> for keys that already exist
    # there. Only update existing files; do not create new ones.
    if LEGACY_SIMULINK_DIR.is_dir():
        for key, value in cleaned.items():
            target = LEGACY_SIMULINK_DIR / key
            if target.is_file():
                try:
                    _atomic_write_text(target, value)
                except Exception as ex:
                    logger.warning("Could not mirror %s: %s", target, ex)


# ----------------------------------------------------------------------------
# parameters.js
# ----------------------------------------------------------------------------

# Match `<alias>: process.env.<ENV> = "<value>",` (trailing comma optional).
_PARAMS_LINE = re.compile(
    r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*'
    r'process\.env\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*'
    r'"((?:[^"\\]|\\.)*)"',
)


def _migrate_params_if_needed() -> None:
    if PARAMS_PATH.exists():
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as ex:
        logger.error("Cannot create %s: %s", CONFIG_DIR, ex)
        raise

    if LEGACY_APP_PARAMS.exists():
        try:
            content = LEGACY_APP_PARAMS.read_text(encoding="utf-8")
            _atomic_write_text(PARAMS_PATH, content)
            logger.info("Seeded %s from %s", PARAMS_PATH, LEGACY_APP_PARAMS)
            return
        except Exception as ex:
            logger.warning("Could not read %s: %s", LEGACY_APP_PARAMS, ex)

    _atomic_write_text(PARAMS_PATH, "module.exports = {\n}\n")


def get_env_parameters() -> "list[dict]":
    _migrate_params_if_needed()
    try:
        text = PARAMS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return _parse_params(text)


def _parse_params(text: str) -> "list[dict]":
    out = []
    for m in _PARAMS_LINE.finditer(text):
        out.append({
            "alias": m.group(1),
            "env": m.group(2),
            "value": _unescape_js(m.group(3)),
        })
    return out


def _unescape_js(s: str) -> str:
    """Unescape a JS double-quoted string body (limited: \\, \", \n, \t)."""
    return (
        s.replace('\\\\', '\x00')
         .replace('\\"', '"')
         .replace('\\n', '\n')
         .replace('\\t', '\t')
         .replace('\x00', '\\')
    )


def _escape_js(s: str) -> str:
    return (
        s.replace('\\', '\\\\')
         .replace('"', '\\"')
         .replace('\n', '\\n')
         .replace('\t', '\\t')
    )


def save_env_parameters(entries: "list[dict]") -> None:
    _migrate_params_if_needed()
    text = _format_params(entries)
    _atomic_write_text(PARAMS_PATH, text)
    if LEGACY_APP_PARAMS.exists():
        try:
            _atomic_write_text(LEGACY_APP_PARAMS, text)
        except Exception as ex:
            logger.warning("Could not mirror to %s: %s", LEGACY_APP_PARAMS, ex)


def _format_params(entries: "list[dict]") -> str:
    valid = []
    for e in (entries or []):
        alias = str(e.get("alias", "")).strip()
        env = str(e.get("env", "")).strip()
        value = str(e.get("value", ""))
        if not alias or not env:
            continue
        valid.append((alias, env, _escape_js(value)))

    lines = ["module.exports = {"]
    for i, (alias, env, esc) in enumerate(valid):
        suffix = "," if i < len(valid) - 1 else ""
        lines.append(f'{alias}: process.env.{env} = "{esc}"{suffix}')
    lines.append("}")
    return "\n".join(lines) + "\n"
