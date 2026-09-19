"""Append the stage-5 UI strings to every ARB.

Run once. Idempotent: a key already present is left exactly as it is, so a
second run cannot overwrite a translation somebody has since corrected by hand.

The template (`app_en.arb`) also gets an `@key` description block, because the
other eight files do not carry them and `l10n.yaml` names English as the
template.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1])
NEW = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
DESCRIPTIONS = NEW.pop("_descriptions")

for code, strings in NEW.items():
    path = ROOT / f"app_{code}.arb"
    data = json.loads(path.read_text(encoding="utf-8"))
    added = []
    for key, value in strings.items():
        if key in data:
            continue
        data[key] = value
        added.append(key)
        if code == "en":
            data[f"@{key}"] = {"description": DESCRIPTIONS[key]}
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{path.name}: +{len(added)}")
