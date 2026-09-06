"""Drive the two cloud model adapters against a real Vertex project.

Not a test. `make check` never runs this and CI has no credentials for it; the
mocks are what the suite exercises (decision 31). This is the thing that has to
be run by hand, once, before anyone believes `OCR_PROVIDER=gemini` works — the
adapters are excluded from coverage precisely because a fake cannot tell you
whether a model in `asia-south1` returns JSON that satisfies
`DocumentExtraction`.

    ./.venv/bin/python scripts/smoke_vertex.py path/to/prescription.jpg

Needs application-default credentials and these four in the environment:
VERTEX_PROJECT, VERTEX_REGION, OCR_MODEL_ID, REPAIR_MODEL_ID — plus
VERTEX_ZDR_ENABLED=true, which is an assertion the operator makes about the
project, not something this script can verify. Read the banner it prints.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.adapters.llm.vertex import VertexRepairProvider  # noqa: E402
from app.adapters.ocr.gemini import GeminiOCRProvider  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.domain.record import DocumentKind  # noqa: E402

BANNER = """\
--------------------------------------------------------------------------
Calling Vertex AI with a real payload. VERTEX_ZDR_ENABLED is an assertion
you are making about this project, not one this code can check. Do not point
it at a real patient's document until Zero Data Retention is confirmed in
writing for {project}/{region}.
--------------------------------------------------------------------------"""

# A payload that fails the 0.2 contract in three ways at once: a status that is
# not in the enum, a field with no value at all, and a hallucination-bait
# free-text answer that must survive verbatim rather than being resolved.
BROKEN = {
    "schema_version": "0.2",
    # Present, and correct. The first run of this script omitted them, and the
    # model supplied "unknown_intake_id" and "unknown_hospital_id" rather than
    # leave a required field out — which is how `IDENTITY_KEYS` in
    # `app/services/repair.py` came to exist. Keep them here: what this script
    # is for now is checking the model leaves them alone when they are there.
    "intake_id": "aa11bb22-0000-4000-8000-00000000dead",
    "hospital_id": "aiia-delhi",
    "fields": [
        {"field_id": "chief_complaint", "status": "ANSWERED!!", "value": "chest pain"},
        {"field_id": "duration"},
        {
            "field_id": "onset",
            "status": "answered",
            "value": "maybe two weeks, could be more",
        },
    ],
}


async def main(image_path: Path) -> int:
    settings = Settings()
    print(BANNER.format(project=settings.vertex_project, region=settings.vertex_region))

    print(f"\n== OCR ({settings.ocr_model_id}) ==")
    ocr = GeminiOCRProvider(settings)
    extraction = await ocr.read(
        image_path.read_bytes(),
        document_id="smoke_ocr_1",
        hint=DocumentKind.PRESCRIPTION,
    )
    print(f"  quality   {extraction.quality} ({extraction.quality_reason or '-'})")
    print(f"  kind      {extraction.kind}")
    print(f"  items     {len(extraction.items)}")
    print(f"  redacted  {extraction.redactions}")
    for item in extraction.items[:6]:
        print(f"    - {item.raw_text!r} conf={item.confidence}")

    print(f"\n== repair ({settings.repair_model_id}) ==")
    repair = VertexRepairProvider(settings)
    repaired = await repair.repair(BROKEN, schema=_schema(), errors=_errors())
    if repaired is None:
        print("  repair returned None — the call failed; see the warning above")
        return 1
    print(json.dumps(repaired, indent=2, ensure_ascii=False)[:1200])

    # The one thing worth asserting by hand: repair must not have resolved the
    # ambiguity. "maybe two weeks" is the patient's answer, and an intake that
    # turns it into "14 days" has invented a clinical fact.
    blob = json.dumps(repaired, ensure_ascii=False)
    ok = True

    if "maybe two weeks" in blob:
        print("\n  original text: kept")
    else:
        print("\n  original text: LOST — the model rewrote it")
        ok = False

    for key in ("intake_id", "hospital_id"):
        if repaired.get(key) == BROKEN[key]:
            print(f"  {key}: unchanged")
        else:
            print(f"  {key}: CHANGED to {repaired.get(key)!r} — repair would be rejected")
            ok = False

    return 0 if ok else 1


def _schema() -> dict:
    from app.contracts.kiosk import KioskIntakeV0_2

    return KioskIntakeV0_2.model_json_schema()


def _errors() -> list[dict]:
    """The real validation errors, not a hand-written approximation.

    The service hands the model whatever pydantic produced; so does this."""
    from pydantic import ValidationError

    from app.contracts.kiosk import KioskIntakeV0_2

    try:
        KioskIntakeV0_2.model_validate(BROKEN)
    except ValidationError as exc:
        return json.loads(exc.json())
    raise SystemExit("BROKEN validates; it is supposed to fail")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    if os.getenv("OCR_PROVIDER") != "gemini":
        print("Set OCR_PROVIDER=gemini REPAIR_PROVIDER=vertex to run this.")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(Path(sys.argv[1]))))
