#!/usr/bin/env python3
"""
Convert GOcontroll-Architecture/controller/static/pinning.md into a structured
JSON for go-web-ui (ModulineWebUI/data/controller_pinning.json).

Run from the repository root:

    python scripts/generate_controller_pinning.py

Optional positional args: <input.md> <output.json>
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT.parent / "GOcontroll-Architecture" / "controller" / "static" / "pinning.md"
DEFAULT_OUTPUT = REPO_ROOT / "ModulineWebUI" / "data" / "controller_pinning.json"

# Map first letter of family code to the slot prefix used elsewhere in the app.
FAMILY_TO_SLOT_PREFIX = {
    "L": "M4S",
    "M": "MMS",
    "HMI": "MDS",
}

# The architecture documentation is in Dutch but the Web UI surfaces this text
# verbatim in English. Override the parsed platforms / connector_label /
# description here so regenerating from updated upstream markdown keeps the UI
# in sync with the actually-shipping product line (L2/L3/L4, M1, HMI1).
ENGLISH_OVERRIDES = {
    "M4S": {
        "platforms": ["L2", "L3", "L4"],
        "connector_label": "Connector C — System connector (26-pin)",
        "description": "Connector C is the fixed interface connector on all Moduline L2, L3 and L4 controllers.",
    },
    "MMS": {
        "platforms": ["M1"],
        "connector_label": "Connectors A and B — Fixed system pins (34-pin per connector)",
        "description": "On the Moduline M1, connectors A and B share space with the module slots.",
    },
    "MDS": {
        "platforms": ["HMI1"],
        "connector_label": "Connector A — Fixed system pins (34-pin)",
        "description": "On the Moduline HMI1, connector A contains both the system pins and the two module slots (MDS1/MDS2).",
    },
}


def family_to_prefix(first_platform: str) -> str:
    p = first_platform.upper()
    if p.startswith("HMI"):
        return "MDS"
    if p.startswith("M"):
        return "MMS"
    if p.startswith("L"):
        return "M4S"
    return ""


def parse_controller_pinning(md: str) -> dict:
    """Parse controller-level pin tables grouped per controller family."""
    out = {}

    # Split on top-level controller-family headings; skip the "Overzicht..." and
    # "Related documents" sections which also start with `## `.
    sections = re.split(
        r"^## (?!Overzicht|Related)",
        md,
        flags=re.MULTILINE,
    )
    for sec in sections[1:]:
        lines = sec.splitlines()
        heading = lines[0].strip()

        m = re.match(r"Moduline\s+(.+)", heading)
        if not m:
            continue
        platforms = [p.strip() for p in m.group(1).split("/")]
        if not platforms:
            continue

        slot_prefix = family_to_prefix(platforms[0])
        if not slot_prefix:
            continue

        # Connector heading (### ... )
        connector_label = ""
        for line in lines[1:]:
            if line.startswith("### "):
                connector_label = line[4:].strip()
                break

        # First non-special paragraph after the section heading == description.
        description = ""
        for raw in lines[1:]:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(("#", "|", "!", ">", "-", ":")):
                continue
            description = line
            break

        # Pin table: 3-column "Pin | Signaal | Omschrijving"
        pins = []
        in_table = False
        for raw in lines:
            line = raw.strip()
            if not in_table:
                if line.startswith("|") and "Pin" in line and "Signaal" in line:
                    in_table = True
                continue
            if line.startswith("|--") or line.startswith("|:--"):
                continue
            if line.startswith("|") and line.endswith("|"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) == 3 and cells[0]:
                    pins.append({
                        "pin": cells[0],
                        "signal": cells[1],
                        "description": cells[2],
                    })
            elif pins:
                in_table = False  # blank line ends the body

        # Connector image: prefer the image whose filename contains 'con' (excludes 3D view)
        imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", sec)
        connector_image = None
        for src in imgs:
            name = Path(src).name.lower()
            if "con" in name and "3d" not in name and "plug" not in name:
                connector_image = "/assets/modules/" + Path(src).name
                break
        if not connector_image and len(imgs) >= 2:
            connector_image = "/assets/modules/" + Path(imgs[1]).name

        overrides = ENGLISH_OVERRIDES.get(slot_prefix, {})

        out[slot_prefix] = {
            "platforms": overrides.get("platforms", platforms),
            "connector_label": overrides.get("connector_label", connector_label),
            "description": overrides.get("description", description),
            "connector_image": connector_image,
            "pins": pins,
        }
    return out


def main():
    inp = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    outp = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT

    if not inp.exists():
        print(f"Input not found: {inp}", file=sys.stderr)
        sys.exit(1)

    text = inp.read_text(encoding="utf-8")
    data = parse_controller_pinning(text)

    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(data)} controller families to {outp}")
    for prefix, info in data.items():
        plat = "/".join(info["platforms"])
        print(f"  {prefix:4s}  {plat:32s}  {len(info['pins'])} pins, image={info['connector_image']}")


if __name__ == "__main__":
    main()
