#!/usr/bin/env python3
"""
Convert GOcontroll-Architecture/modules/pinning.md into a structured JSON
shipped with go-web-ui (ModulineWebUI/data/module_pinning.json).

Run from the repository root:

    python scripts/generate_module_pinning.py

Optional positional args: <input.md> <output.json>
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT.parent / "GOcontroll-Architecture" / "modules" / "pinning.md"
DEFAULT_OUTPUT = REPO_ROOT / "ModulineWebUI" / "data" / "module_pinning.json"


def parse_pinning_md(text: str) -> dict:
    """Parse pinning.md into {type_code: {name, slots, pins}}.

    type_code is the 6-digit module type (e.g. '202002').
    pins is a list of {function, description, pins[]} where pins[] aligns with slots.
    """
    out = {}
    # split on '### ' headings; first chunk is preamble
    chunks = re.split(r"^### ", text, flags=re.MULTILINE)
    for chunk in chunks[1:]:
        lines = chunk.splitlines()
        if not lines:
            continue
        title = lines[0].strip()

        m = re.search(r"\*\*Artikelnummer:\*\*\s*(\d{6})", chunk)
        if not m:
            continue
        type_code = m.group(1)

        # collect first contiguous markdown table
        table_lines = []
        in_table = False
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("|"):
                table_lines.append(stripped)
                in_table = True
            elif in_table:
                break
        if len(table_lines) < 3:
            continue

        header = [c.strip() for c in table_lines[0].strip("|").split("|")]
        # table_lines[1] is alignment row -> skip
        slot_cols = header[2:]  # after Functie, Omschrijving

        pins = []
        for raw in table_lines[2:]:
            cells = [c.strip() for c in raw.strip("|").split("|")]
            if len(cells) != len(header):
                continue
            pins.append({
                "function": cells[0],
                "description": cells[1],
                "pins": cells[2:],
            })

        out[type_code] = {
            "name": title,
            "slots": slot_cols,
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
    data = parse_pinning_md(text)

    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(data)} modules to {outp}")
    for code, mod in data.items():
        print(f"  {code}  {mod['name']:38s}  {len(mod['pins'])} pins, {len(mod['slots'])} slots")


if __name__ == "__main__":
    main()
