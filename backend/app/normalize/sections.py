"""Which section of the history a kiosk field belongs to.

Pure lookup. The kiosk may state a section on the field itself, and when it does
that wins — the device knows what it asked. This table is the fallback for the
fields it does not label, and it exists so a new field id lands somewhere
sensible instead of vanishing.

An unrecognised field falls to `HPI`, which is the section a physician reads
first. It is never dropped: an unmapped field on the report is a question a
clinician can answer; an unmapped field silently discarded is not.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.domain.clinical.enums import Section

#: Exact field ids the Jetson's extractor is known to emit.
FIELD_SECTIONS: Mapping[str, Section] = {
    # identity
    "age": Section.IDENTITY,
    "sex": Section.IDENTITY,
    "reporter": Section.IDENTITY,
    # The app answers "who is this for?" on its own screen and seeds the
    # bundle's question from it, so the same statement arrives twice: once at
    # the record root, once as this field. Identity is not a body section, so
    # filing it here keeps it out of the report rather than printing
    # "general.reporter: self" under history of present illness.
    "general.reporter": Section.IDENTITY,
    "preferred_language": Section.IDENTITY,
    # chief complaint
    "chief_complaint": Section.CHIEF_COMPLAINT,
    "complaint_site": Section.CHIEF_COMPLAINT,
    # history of present illness
    "duration": Section.HPI,
    "onset": Section.HPI,
    "severity": Section.HPI,
    "character": Section.HPI,
    "radiation": Section.HPI,
    "progression": Section.HPI,
    "timing": Section.HPI,
    "aggravating_factors": Section.HPI,
    "relieving_factors": Section.HPI,
    "associated_symptoms": Section.HPI,
    "previous_episodes": Section.HPI,
    # past history
    "past_medical_history": Section.PAST_MEDICAL,
    "known_diabetes": Section.PAST_MEDICAL,
    "known_hypertension": Section.PAST_MEDICAL,
    "known_asthma": Section.PAST_MEDICAL,
    "known_thyroid_disorder": Section.PAST_MEDICAL,
    "past_surgery": Section.PAST_SURGICAL,
    "hospitalisation": Section.PAST_SURGICAL,
    # drugs and allergies
    "current_medications": Section.MEDICATIONS,
    "ayurvedic_medications": Section.MEDICATIONS,
    "adherence": Section.MEDICATIONS,
    "drug_allergy": Section.ALLERGIES,
    "food_allergy": Section.ALLERGIES,
    "allergy": Section.ALLERGIES,
    # family and personal
    "family_history": Section.FAMILY_HISTORY,
    "diet": Section.PERSONAL_HISTORY,
    "appetite": Section.PERSONAL_HISTORY,
    "sleep": Section.PERSONAL_HISTORY,
    "bowel_habit": Section.PERSONAL_HISTORY,
    "bladder_habit": Section.PERSONAL_HISTORY,
    "tobacco": Section.PERSONAL_HISTORY,
    "alcohol": Section.PERSONAL_HISTORY,
    "occupation": Section.PERSONAL_HISTORY,
    "menstrual_history": Section.PERSONAL_HISTORY,
    "pregnancy": Section.PERSONAL_HISTORY,
    # ayurveda, patient-reported only
    "prakriti_self_report": Section.AYURVEDA,
    "agni": Section.AYURVEDA,
    "koshtha": Section.AYURVEDA,
    "nidra": Section.AYURVEDA,
    "mala": Section.AYURVEDA,
    "mutra": Section.AYURVEDA,
    # red-flag screening answers
    "breathlessness": Section.RED_FLAG_SCREEN,
    "chest_pain": Section.RED_FLAG_SCREEN,
    "bleeding": Section.RED_FLAG_SCREEN,
    "loss_of_consciousness": Section.RED_FLAG_SCREEN,
    "altered_sensorium": Section.RED_FLAG_SCREEN,
    "weight_loss": Section.RED_FLAG_SCREEN,
    "fever_duration": Section.RED_FLAG_SCREEN,
    # investigations arrive from documents
    "prior_investigations": Section.INVESTIGATIONS,
}

#: Prefix rules, applied when the exact id is unknown. Ordered longest-first at
#: lookup so `allergy_drug_` beats `allergy_`.
PREFIX_SECTIONS: Mapping[str, Section] = {
    "ros_": Section.REVIEW_OF_SYSTEMS,
    "allergy_": Section.ALLERGIES,
    "medication_": Section.MEDICATIONS,
    "condition_": Section.PAST_MEDICAL,
    "diagnosis_": Section.PAST_MEDICAL,
    "surgery_": Section.PAST_SURGICAL,
    "family_": Section.FAMILY_HISTORY,
    "ayurveda_": Section.AYURVEDA,
    "lab_": Section.INVESTIGATIONS,
    "screen_": Section.RED_FLAG_SCREEN,
    "redflag_": Section.RED_FLAG_SCREEN,
}

DEFAULT_SECTION = Section.HPI


def section_for(field_id: str, declared: str | None = None) -> Section:
    """The section `field_id` is filed under.

    A `declared` section from the kiosk wins when it names a section we know.
    One we do not know is ignored rather than raising: a device on a newer
    content version must not be able to fail an ingest by naming a section this
    build has not heard of.
    """
    if declared:
        try:
            return Section(declared)
        except ValueError:
            pass
    exact = FIELD_SECTIONS.get(field_id)
    if exact is not None:
        return exact
    for prefix in sorted(PREFIX_SECTIONS, key=len, reverse=True):
        if field_id.startswith(prefix):
            return PREFIX_SECTIONS[prefix]
    return DEFAULT_SECTION
