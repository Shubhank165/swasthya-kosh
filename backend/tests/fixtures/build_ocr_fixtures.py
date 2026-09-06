"""Generate the OCR fixture files.

    python tests/fixtures/build_ocr_fixtures.py

Fixtures are keyed by a hash of their image bytes, so the bytes and the JSON
have to be generated together or the lookup silently misses. This script owns
both. Re-running it is a no-op unless a fixture body changed.

The extraction bodies are transcriptions of what the seven-model benchmark
produced on the thirteen-page corpus, retyped with every identifier removed —
including the `900.2`-for-`100.2` misreading, which is here because it happened,
not because it makes a good test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.adapters.ocr.mock import fixture_key

FIXTURES_DIR = Path(__file__).parent / "ocr"

#: Deterministic stand-in bytes per fixture. Never a real document — a
#: photographed prescription in a public repository is a patient's data in a
#: public repository, whatever the licence says.
IMAGES: dict[str, bytes] = {
    "prescription_clean": b"MEDIKIOSK-FIXTURE-IMAGE:prescription_clean" + b"\x00" * 96,
    "prescription_lowconf": b"MEDIKIOSK-FIXTURE-IMAGE:prescription_lowconf" + b"\x00" * 96,
    "lab_report": b"MEDIKIOSK-FIXTURE-IMAGE:lab_report" + b"\x00" * 96,
    "discharge_summary": b"MEDIKIOSK-FIXTURE-IMAGE:discharge_summary" + b"\x00" * 96,
    "contains_aadhaar": b"MEDIKIOSK-FIXTURE-IMAGE:contains_aadhaar" + b"\x00" * 96,
}


def _bbox(x: float, y: float, w: float = 0.6, h: float = 0.04) -> dict[str, float]:
    return {"x": x, "y": y, "width": w, "height": h}


EXTRACTIONS: dict[str, dict[str, Any]] = {
    "prescription_clean": {
        "kind": "prescription",
        "page_count": 1,
        "overall_confidence": 0.94,
        "document_date": "2026-08-14",
        "issuing_facility": "All India Institute of Ayurveda OPD",
        "page_text": [
            "All India Institute of Ayurveda OPD\n"
            "Date: 14/08/2026\n"
            "Rx\n"
            "1. Tab. Metformin 500 mg BD x 30 days\n"
            "2. Tab. Amlodipine 5 mg OD x 30 days\n"
            "3. Tab. Ecosprin 75 mg OD x 30 days\n"
            "4. Tab. Clopidogrel 75 mg OD x 30 days\n"
            "5. Cap. Omeprazole 20 mg OD x 14 days\n"
        ],
        "items": [
            {
                "item_id": "item_rx1",
                "kind": "medicine",
                "raw_text": "Tab. Metformin 500 mg BD x 30 days",
                "page": 1,
                "bbox": _bbox(0.10, 0.32),
                "confidence": 0.96,
                "medicine": {
                    "name": "Metformin",
                    "dose_magnitude": 500,
                    "dose_unit": "mg",
                    "frequency": "BD",
                    "duration": "30 days",
                    "ingredient_key": "metformin",
                },
            },
            {
                "item_id": "item_rx2",
                "kind": "medicine",
                "raw_text": "Tab. Amlodipine 5 mg OD x 30 days",
                "page": 1,
                "bbox": _bbox(0.10, 0.38),
                "confidence": 0.95,
                "medicine": {
                    "name": "Amlodipine",
                    "dose_magnitude": 5,
                    "dose_unit": "mg",
                    "frequency": "OD",
                    "duration": "30 days",
                    "ingredient_key": "amlodipine",
                },
            },
            {
                "item_id": "item_rx3",
                "kind": "medicine",
                "raw_text": "Tab. Ecosprin 75 mg OD x 30 days",
                "page": 1,
                "bbox": _bbox(0.10, 0.44),
                "confidence": 0.93,
                "medicine": {
                    "name": "Ecosprin",
                    "dose_magnitude": 75,
                    "dose_unit": "mg",
                    "frequency": "OD",
                    "duration": "30 days",
                    "ingredient_key": "aspirin",
                },
            },
            {
                # Clopidogrel with omeprazole: a sourced, moderate interaction,
                # and a pair that genuinely turns up together on Indian OPD
                # prescriptions. It is here so the interaction path has
                # something to find on a realistic document rather than a
                # contrived one.
                "item_id": "item_rx4",
                "kind": "medicine",
                "raw_text": "Tab. Clopidogrel 75 mg OD x 30 days",
                "page": 1,
                "bbox": _bbox(0.10, 0.50),
                "confidence": 0.94,
                "medicine": {
                    "name": "Clopidogrel",
                    "dose_magnitude": 75,
                    "dose_unit": "mg",
                    "frequency": "OD",
                    "duration": "30 days",
                    "ingredient_key": "clopidogrel",
                },
            },
            {
                "item_id": "item_rx5",
                "kind": "medicine",
                "raw_text": "Cap. Omeprazole 20 mg OD x 14 days",
                "page": 1,
                "bbox": _bbox(0.10, 0.56),
                "confidence": 0.92,
                "medicine": {
                    "name": "Omeprazole",
                    "dose_magnitude": 20,
                    "dose_unit": "mg",
                    "frequency": "OD",
                    "duration": "14 days",
                    "ingredient_key": "omeprazole",
                },
            },
        ],
    },
    # The digit failure the benchmark actually produced: ९००.२ read for १००.२.
    # Below the confidence floor, so it comes back needs_verification.
    "prescription_lowconf": {
        "kind": "prescription",
        "page_count": 1,
        "overall_confidence": 0.61,
        "page_text": [
            "पर्चा\nदिनांक: 20/08/2026\n1. टैब. मेटफॉर्मिन 900.2 मि.ग्रा. दिन में दो बार\n"
        ],
        "items": [
            {
                "item_id": "item_lc1",
                "kind": "medicine",
                "raw_text": "टैब. मेटफॉर्मिन 900.2 मि.ग्रा. दिन में दो बार",
                "page": 1,
                "bbox": _bbox(0.08, 0.30),
                # Below OCR_CONFIDENCE_FLOOR. A wrong digit in a dose is the
                # most dangerous error this system can make, so it renders
                # distinctly with the raw text beside it.
                "confidence": 0.58,
                "medicine": {
                    "name": "Metformin",
                    "dose_magnitude": 900.2,
                    "dose_unit": "mg",
                    "frequency": "BD",
                    "ingredient_key": "metformin",
                },
            }
        ],
    },
    "lab_report": {
        "kind": "lab_report",
        "page_count": 1,
        "overall_confidence": 0.97,
        "document_date": "2026-08-28",
        "issuing_facility": "Central Pathology Laboratory",
        "page_text": [
            "Central Pathology Laboratory\n"
            "Haemoglobin        9.8 g/dL      (12.0 - 15.0 g/dL)\n"
            "Fasting glucose    148 mg/dL     (70 - 100 mg/dL)\n"
            "Serum ferritin     18 ng/mL      \n"
        ],
        "items": [
            {
                "item_id": "item_lab1",
                "kind": "lab_result",
                "raw_text": "Haemoglobin 9.8 g/dL (12.0 - 15.0 g/dL)",
                "page": 1,
                "bbox": _bbox(0.08, 0.24),
                "confidence": 0.97,
                "lab_result": {
                    "analyte": "Haemoglobin",
                    "value": 9.8,
                    "unit": "g/dL",
                    "reference_range": {
                        "low": 12.0,
                        "high": 15.0,
                        "unit": "g/dL",
                        "raw_text": "12.0 - 15.0 g/dL",
                    },
                },
            },
            {
                "item_id": "item_lab2",
                "kind": "lab_result",
                "raw_text": "Fasting glucose 148 mg/dL (70 - 100 mg/dL)",
                "page": 1,
                "bbox": _bbox(0.08, 0.30),
                "confidence": 0.96,
                "lab_result": {
                    "analyte": "Fasting glucose",
                    "value": 148,
                    "unit": "mg/dL",
                    "reference_range": {
                        "low": 70,
                        "high": 100,
                        "unit": "mg/dL",
                        "raw_text": "70 - 100 mg/dL",
                    },
                },
            },
            {
                # No range printed on this line. It must come back
                # `range_unavailable` and must NOT be flagged — comparing it
                # against a range from anywhere else would be manufacturing a
                # finding out of a formatting gap.
                "item_id": "item_lab3",
                "kind": "lab_result",
                "raw_text": "Serum ferritin 18 ng/mL",
                "page": 1,
                "bbox": _bbox(0.08, 0.36),
                "confidence": 0.95,
                "lab_result": {
                    "analyte": "Serum ferritin",
                    "value": 18,
                    "unit": "ng/mL",
                },
            },
        ],
    },
    "discharge_summary": {
        "kind": "discharge_summary",
        "page_count": 1,
        "overall_confidence": 0.91,
        "document_date": "2026-06-02",
        "page_text": [
            "Discharge Summary\n"
            "Final diagnosis: Type 2 diabetes mellitus\n"
            "Procedure: Laparoscopic cholecystectomy\n"
        ],
        "items": [
            {
                "item_id": "item_dx1",
                "kind": "diagnosis",
                "raw_text": "Final diagnosis: Type 2 diabetes mellitus",
                "page": 1,
                "bbox": _bbox(0.08, 0.22),
                "confidence": 0.93,
                "label": "known diabetes",
            },
            {
                "item_id": "item_px1",
                "kind": "procedure",
                "raw_text": "Procedure: Laparoscopic cholecystectomy",
                "page": 1,
                "bbox": _bbox(0.08, 0.28),
                "confidence": 0.90,
                "label": "cholecystectomy",
            },
        ],
    },
    # The leak the benchmark corpus actually produced. The numbers below are
    # invented and belong to nobody; what matters is the shape.
    "contains_aadhaar": {
        "kind": "prescription",
        "page_count": 1,
        "overall_confidence": 0.88,
        "page_text": [
            "Patient: [name]\nAadhaar: 4321 8765 2108\nMobile: 9876543210\n"
            "Rx: Tab. Metformin 500 mg BD\n"
        ],
        "items": [
            {
                "item_id": "item_leak1",
                "kind": "other",
                "raw_text": "Aadhaar: 4321 8765 2108  Mobile: 9876543210",
                "page": 1,
                "bbox": _bbox(0.08, 0.12),
                "confidence": 0.88,
            },
            {
                "item_id": "item_leak2",
                "kind": "medicine",
                "raw_text": "Tab. Metformin 500 mg BD",
                "page": 1,
                "bbox": _bbox(0.08, 0.30),
                "confidence": 0.94,
                "medicine": {
                    "name": "Metformin",
                    "dose_magnitude": 500,
                    "dose_unit": "mg",
                    "frequency": "BD",
                    "ingredient_key": "metformin",
                },
            },
        ],
    },
}


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, str] = {}
    for name, image in IMAGES.items():
        key = fixture_key(image)
        index[name] = key
        path = FIXTURES_DIR / f"{key}.json"
        body = dict(EXTRACTIONS[name])
        body["_fixture_name"] = name
        path.write_text(
            json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{name:24} -> {path.name}")
    (FIXTURES_DIR / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
