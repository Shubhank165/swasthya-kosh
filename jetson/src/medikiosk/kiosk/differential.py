"""Turns the facts the voice interview collected into a ranked differential and a FHIR bundle.

The interview stays as it is - multilingual, spoken, driven by the deterministic state machine.
This only takes what it established and asks the entropy engine what those findings point at, so
the doctor gets a ranked differential with ICD-10 codes instead of a bare list of symptoms.

The engine is scored, not consulted for questions: our 184-node knowledge base is English-only,
and a kiosk that speaks nine languages must not start asking in one. Mapping our fields onto its
nodes gives the clinical depth without giving up the language coverage.

Nothing here changes triage. Red flags are still decided by clinical/red_flags.py, whose rules are
auditable line by line; a probability from a scoring matrix never promotes or suppresses an alert.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from medikiosk.models import PatientState

# Our PatientState field -> the engine node whose weights encode the same finding.
#
# Every pair here was checked against the node's actual prompt text, because a plausible-looking
# mapping is worse than none. `sweating` is deliberately absent: the only sweating nodes are
# drenching NIGHT sweats (a tuberculosis / lymphoma B-symptom) and paroxysmal sweating with
# hypertension (phaeochromocytoma). Neither is the diaphoresis of a myocardial infarction, and
# mapping to the first one ranked Pulmonary TB and Lymphoma at 50% each for a textbook MI
# presentation while STEMI scored zero.
FIELD_NODES: tuple[tuple[str, str], ...] = (
    ("chest_pain", "ROS_CVS_001"),          # chest pain, tightness or pressure
    ("breathlessness", "ROS_RES_005"),      # chest tightness / difficulty taking a deep breath
    ("fever", "ROS_CON_001"),               # fever or felt feverish recently
    ("vomiting", "ROS_GI_001"),             # nausea or vomiting
    ("pain_radiation", "OC_006"),           # does this symptom radiate or spread
    ("altered_consciousness", "ROS_NEU_009"),  # loss of consciousness, even briefly
    ("speech_difficulty", "ROS_NEU_007"),   # change in speech, slurring
    ("one_sided_weakness", "T008"),         # FAST signs: facial droop, arm weakness
    ("active_bleeding", "T005"),            # active uncontrolled external bleeding
)


def _engine():
    from medikiosk.engine import ensure_database
    from medikiosk.engine.math_engine import EntropyEngine

    # The knowledge base is a build artefact - *.db is gitignored so patient records cannot be
    # committed - so a fresh clone has to build it before the first differential.
    ensure_database()
    return EntropyEngine()


def _node_types(engine) -> dict[str, str]:
    return {node_id: node["ui_type"] for node_id, node in engine._load_nodes().items()}


def _as_answer(value: bool, ui_type: str) -> Any | None:
    """Shape one of our booleans for a node's widget type, or None when it cannot be expressed.

    Only BINARY nodes can carry a denial: normalise_answer maps False to -0.5 there, but for
    SINGLE_SELECT it returns YES for *any* value that is not None or "" - so passing False would
    score a patient who denied fever as having it. Negatives on select-type nodes are therefore
    dropped rather than guessed at.
    """

    if ui_type == "BINARY":
        return value
    if not value:
        return None
    return ["reported"] if ui_type in ("MULTI_SELECT", "BODY_MAP") else "reported"


def build(state: PatientState, top_n: int = 5) -> dict[str, Any] | None:
    """Rank the syndromes the collected findings point at. None when nothing was established."""

    stated = [(field, node) for field, node in FIELD_NODES if getattr(state, field) is not None]
    if not stated:
        return None

    try:
        engine = _engine()
        types = _node_types(engine)
        session_state: dict[str, Any] = {"scores": {}, "answers": {}, "asked": []}
        answered = []
        for field, node_id in stated:
            answer = _as_answer(getattr(state, field), types.get(node_id, "BINARY"))
            if answer is None:
                continue
            engine.update_scores(session_state, node_id, answer)
            answered.append((field, node_id))
        if not answered:
            return None
        ranked = engine.build_differential(session_state, top_n=top_n)
    except Exception as error:
        # A missing or unreadable knowledge base must cost the differential, not the intake.
        return {"error": f"{type(error).__name__}: {error}", "ranked": []}

    # The softmax saturates hard on few inputs - three findings routinely produce a 1.000 leader.
    # The engine is built to run after a dozen entropy-selected questions; our voice interview
    # feeds it a handful, so the numbers rank the possibilities but do not calibrate them. Say
    # that next to the number rather than letting a doctor read 1.000 as certainty.
    count = len(answered)
    return {
        "ranked": ranked,
        "from_findings": [field for field, _ in answered],
        "findings_count": count,
        "confidence": "low" if count < 5 else "moderate",
        "disclaimer": (
            f"Ranking only, from {count} patient-reported finding(s). Probabilities are relative "
            "weights from a deterministic scoring matrix, not calibrated likelihoods, and are "
            "unreliable on this few inputs. Not a diagnosis; for clinician review only."
        ),
    }


def fhir_bundle(state: PatientState, differential: dict[str, Any] | None) -> dict[str, Any]:
    """A FHIR R4 Bundle carrying the patient and the ranked conditions, for the hospital system."""

    entries: list[dict[str, Any]] = [
        {
            "resource": {
                "resourceType": "Patient",
                "id": "kiosk-patient",
                # No name, no identifier: the kiosk holds an ABHA hash, and a FHIR bundle leaving
                # the device is the last place to put an identifier back in.
                "extension": [
                    {
                        "url": "http://hl7.org/fhir/StructureDefinition/patient-age",
                        "valueInteger": state.age_years,
                    }
                ]
                if state.age_years is not None
                else [],
            }
        }
    ]

    for rank, item in enumerate((differential or {}).get("ranked", []), start=1):
        entries.append(
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": f"differential-{rank}",
                    "verificationStatus": {
                        "coding": [
                            {
                                "system": (
                                    "http://terminology.hl7.org/CodeSystem/"
                                    "condition-ver-status"
                                ),
                                # Never "confirmed": these are kiosk-derived probabilities.
                                "code": "provisional",
                            }
                        ]
                    },
                    "code": {
                        "coding": [
                            {
                                "system": "http://hl7.org/fhir/sid/icd-10",
                                "code": item.get("icd10", ""),
                                "display": item.get("name", ""),
                            }
                        ]
                    },
                    "subject": {"reference": "Patient/kiosk-patient"},
                    "note": [{"text": f"probability {item.get('probability')}, rank {rank}"}],
                }
            }
        )

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry": entries,
    }
