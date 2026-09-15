"""Step 8: the sheet the doctor reads, and which queue the patient joins.

Routing is a lookup table on the complaint plus the red flags already raised, for the same reason
the red-flag rules are hardcoded: a queue assignment is a triage decision, and a triage decision
made by a 1B model is not auditable. Every routing here can be pointed at the line that produced
it. Anything the table does not recognise goes to General Medicine, which is the correct place for
an undifferentiated complaint - not a guess dressed up as a specialty.

The report deliberately shows gaps. Unanswered questions, the three Dashavidha parameters a kiosk
cannot assess, and documents that OCR read poorly are all printed as pending rather than dropped,
because a doctor needs to know what the kiosk did not find out.
"""

from __future__ import annotations

from datetime import datetime, timezone

from medikiosk.kiosk.provenance import Ledger
from medikiosk.models import PatientState, RedFlagAlert, Urgency

EMERGENCY_QUEUE = "Emergency"
DEFAULT_QUEUE = "General Medicine"

# Complaint keyword -> specialist queue. Hindi terms sit beside English because the complaint is
# stored in whatever language the patient used.
ROUTING: tuple[tuple[tuple[str, ...], str], ...] = (
    (("chest", "cardiac", "palpitation", "सीने", "छाती", "धड़कन"), "Cardiology"),
    (("breath", "cough", "asthma", "wheez", "साँस", "सांस", "खांसी", "खाँसी"), "Pulmonology"),
    (
        ("abdomen", "abdominal", "stomach", "belly", "vomit", "diarrh", "पेट", "उल्टी", "दस्त"),
        "Gastroenterology",
    ),
    (
        ("head", "migraine", "seizure", "fit", "faint", "dizz", "सिर", "चक्कर", "मिर्गी"),
        "Neurology",
    ),
    (
        ("ankle", "knee", "back", "joint", "bone", "fracture", "shoulder", "sprain",
         "घुटन", "पीठ", "कमर", "जोड़", "हड्डी", "कंध"),
        "Orthopaedics",
    ),
    (("eye", "vision", "आँख", "आंख", "दृष्टि"), "Ophthalmology"),
    (("ear", "throat", "nose", "कान", "गला", "नाक"), "ENT"),
    (("skin", "rash", "itch", "त्वचा", "खुजली", "चकत्त"), "Dermatology"),
    (("tooth", "teeth", "dental", "gum", "दांत", "दाँत", "मसूड़"), "Dentistry"),
    (
        ("pregnan", "menstru", "period", "गर्भ", "मासिक", "प्रसव"),
        "Obstetrics and Gynaecology",
    ),
)


def route(
    state: PatientState,
    red_flags: list[RedFlagAlert],
    prefers_ayush: bool = False,
) -> dict:
    """Which queue, and why. Emergency always wins; an Ayush request never overrides it.

    Answering the Dashavidha questionnaire is not the same as asking for an Ayurvedic
    consultation - the questionnaire runs for everyone at an Ayush facility. Only an explicit
    patient preference moves them off the clinical specialist queue, or a knee complaint would be
    routed away from Orthopaedics purely because the patient answered eight constitution questions.
    """

    if any(flag.urgency is Urgency.EMERGENCY for flag in red_flags):
        return {
            "queue": EMERGENCY_QUEUE,
            "priority": Urgency.EMERGENCY.value,
            "reason": "Red flag rule fired: " + ", ".join(flag.rule_id for flag in red_flags),
        }

    complaint = (state.complaint or "").lower()
    matched = DEFAULT_QUEUE
    reason = "No specific complaint keyword matched; undifferentiated complaint."
    for terms, queue in ROUTING:
        hit = next((term for term in terms if term in complaint), None)
        if hit:
            matched, reason = queue, f"Complaint matched '{hit}'."
            break

    urgent = any(flag.urgency is Urgency.URGENT for flag in red_flags)
    if prefers_ayush:
        # A patient who came for Ayurvedic care still gets the specialist noted, so the vaidya can
        # refer without a second intake.
        return {
            "queue": "Ayush OPD",
            "priority": Urgency.URGENT.value if urgent else Urgency.ROUTINE.value,
            "reason": f"Patient chose Ayurvedic consultation. {reason}",
            "also_indicated": matched,
        }
    return {
        "queue": matched,
        "priority": Urgency.URGENT.value if urgent else Urgency.ROUTINE.value,
        "reason": reason,
    }


def missing_fields(state: PatientState) -> list[str]:
    """Intake slots left empty, so the doctor sees what was not established."""

    checked = (
        "complaint", "duration", "severity", "age_years",
        "fever", "vomiting", "breathlessness", "active_bleeding",
    )
    return [name for name in checked if getattr(state, name) is None]


def build(
    state: PatientState,
    red_flags: list[RedFlagAlert],
    ayurveda: dict | None = None,
    prakriti: dict | None = None,
    documents: list[dict] | None = None,
    abha_number: str | None = None,
    on_behalf_of: str | None = None,
    past_visits: list[dict] | None = None,
    prefers_ayush: bool = False,
    ledger: Ledger | None = None,
) -> dict:
    documents = documents or []
    past_visits = past_visits or []
    from medikiosk.kiosk import differential as differential_engine

    differential = differential_engine.build(state)
    fhir = differential_engine.fhir_bundle(state, differential)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "patient": {
            # Last four digits only: enough for staff to match the card in hand, not enough to be
            # a usable identifier if this sheet is left on a desk.
            "abha_last4": abha_number[-4:] if abha_number else None,
            "age_years": state.age_years,
            "language": state.detected_language,
            "reported_by": on_behalf_of or "self",
            "previous_visits": len(past_visits),
            "last_visit": past_visits[0].get("recorded_at") if past_visits else None,
        },
        "clinical": {
            "complaint": state.complaint,
            "duration": state.duration,
            "severity": state.severity,
            "findings": {
                name: getattr(state, name)
                for name in (
                    "fever", "vomiting", "breathlessness", "chest_pain", "pain_radiation",
                    "sweating", "active_bleeding", "altered_consciousness",
                    "one_sided_weakness", "speech_difficulty",
                )
                if getattr(state, name) is not None
            },
            "medications": state.medications,
            "allergies": state.allergies,
            "not_established": missing_fields(state),
        },
        "red_flags": [flag.model_dump(mode="json") for flag in red_flags],
        # Ranked by the deterministic entropy engine over the findings above. It informs the
        # doctor; it never decides triage - that stays with the red-flag rules.
        "differential": differential,
        "fhir": fhir,
        "ayurveda": ayurveda,
        # Constitution, from the once-in-a-lifetime Ayush questionnaire. May have been
        # recorded on an earlier visit - "recorded_at" says which.
        "prakriti": prakriti,
        "documents": documents,
        "routing": route(state, red_flags, prefers_ayush),
        # Where each value came from, and which of them a clinician should check before
        # relying on it. A sheet that flattens a spoken answer and an OCR guess into one
        # list invites the reader to trust them equally.
        "provenance": (
            {
                **ledger.summary(),
                "review": [e.model_dump(mode="json") for e in ledger.review_queue()],
                "entries": [e.model_dump(mode="json") for e in ledger.entries],
            }
            if ledger is not None
            else None
        ),
        "verbatim": state.original_transcripts,
        "disclaimer": (
            "Kiosk intake only. Not a diagnosis. All findings are patient-reported and require "
            "clinician confirmation."
        ),
    }
