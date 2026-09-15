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


#: The app bundle's namespaced field ids — `<namespace>.<question>`.
#:
#: The table above was written against the Jetson extractor's bare field names
#: (`age`, `diet`, `sleep`). The compiled question bundle emits dotted ids
#: instead, none of which match a bare name and none of which match a prefix
#: rule — `ayush.` is not `ayurveda_`. Every one of them therefore fell to
#: `DEFAULT_SECTION`, which is how one intake came to render thirty-four lines
#: under *History of presenting illness* with an empty *Ayurveda* section
#: beneath it, and with the patient's age and family history filed as features
#: of today's complaint.
#:
#: Kept as a separate mapping rather than merged above, because the two have
#: different authors and different lifetimes: that one tracks what the kiosk's
#: extractor emits, this one tracks what `clinical/questioning/` compiles to.
BUNDLE_FIELD_SECTIONS: Mapping[str, Section] = {
    # chief complaint
    "routing.chief_complaint": Section.CHIEF_COMPLAINT,
    "routing.complaints": Section.CHIEF_COMPLAINT,
    # identity
    "general.age": Section.IDENTITY,
    "general.sex": Section.IDENTITY,
    # hpi
    "bowel.blood_in_stool": Section.HPI,
    "bowel.consistency": Section.HPI,
    "bowel.incomplete_evacuation": Section.HPI,
    "bowel.stool_frequency": Section.HPI,
    "digestive.acidity": Section.HPI,
    "digestive.appetite_change": Section.HPI,
    "digestive.nausea": Section.HPI,
    "digestive.relation_to_food": Section.HPI,
    "fatigue.effect_on_activity": Section.HPI,
    "fatigue.weight_change": Section.HPI,
    "fever.chills": Section.HPI,
    "fever.fever_pattern": Section.HPI,
    "fever.maximum_temperature": Section.HPI,
    "fever.measured": Section.HPI,
    "fixed.timeline": Section.HPI,
    "general.aggravating": Section.HPI,
    "general.duration": Section.HPI,
    "general.onset": Section.HPI,
    "general.pattern": Section.HPI,
    "general.previous_episodes": Section.HPI,
    "general.progression": Section.HPI,
    "general.relieving": Section.HPI,
    "general.severity": Section.HPI,
    "general.treatment_tried": Section.HPI,
    "headache.character": Section.HPI,
    "headache.light_sound_sensitivity": Section.HPI,
    "headache.site": Section.HPI,
    "headache.vision_change": Section.HPI,
    "joint.joints_affected": Section.HPI,
    "joint.movement_limited": Section.HPI,
    "joint.stiffness_timing": Section.HPI,
    "joint.swelling": Section.HPI,
    "mental.appetite_or_sleep_affected": Section.HPI,
    "mental.effect_on_daily_life": Section.HPI,
    "mental.mood": Section.HPI,
    "other.description": Section.HPI,
    "pain.character": Section.HPI,
    "pain.radiation": Section.HPI,
    "pain.site": Section.HPI,
    "respiratory.breathlessness": Section.HPI,
    "respiratory.cough_type": Section.HPI,
    "respiratory.sputum_colour": Section.HPI,
    "respiratory.wheeze": Section.HPI,
    "skin.distribution": Section.HPI,
    "skin.itching": Section.HPI,
    "skin.lesion_type": Section.HPI,
    "skin.spreading": Section.HPI,
    "sleep.difficulty": Section.HPI,
    "sleep.hours": Section.HPI,
    "sleep.refreshed": Section.HPI,
    "urinary.blood_in_urine": Section.HPI,
    "urinary.burning": Section.HPI,
    "urinary.frequency_change": Section.HPI,
    "urinary.night_urination": Section.HPI,
    "urinary.urine_colour": Section.HPI,
    # past medical
    "general.known_conditions": Section.PAST_MEDICAL,
    # past surgical
    "general.past_surgery": Section.PAST_SURGICAL,
    # medications
    "general.current_medications": Section.MEDICATIONS,
    # allergies
    "general.allergies": Section.ALLERGIES,
    # family history
    "general.family_history": Section.FAMILY_HISTORY,
    # personal history
    "general.alcohol": Section.PERSONAL_HISTORY,
    "general.pregnancy": Section.PERSONAL_HISTORY,
    "general.tobacco": Section.PERSONAL_HISTORY,
    "menstrual.cycle_length": Section.PERSONAL_HISTORY,
    "menstrual.cycle_regular": Section.PERSONAL_HISTORY,
    "menstrual.flow": Section.PERSONAL_HISTORY,
    "menstrual.last_period": Section.PERSONAL_HISTORY,
    "menstrual.pain_with_periods": Section.PERSONAL_HISTORY,
    # ayurveda — no explicit entries. The module's 62 questions all carry the
    # `ayush.` namespace and are routed by the prefix rule below, which is the
    # rule that was already the safety net for them. Fifteen ids were listed
    # here when the module had fifteen questions; none of those ids survived
    # the module being rewritten, so listing ids individually was a promise
    # this file could not keep across a content change.
    # red flag screen
    "bleeding.amount": Section.RED_FLAG_SCREEN,
    "bleeding.ongoing": Section.RED_FLAG_SCREEN,
    "bleeding.site": Section.RED_FLAG_SCREEN,
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
    # The bundle's Ayurveda namespace. A safety net for an `ayush.` question
    # added to the content without an entry in `BUNDLE_FIELD_SECTIONS`: it
    # lands under Ayurveda with a plain label rather than under HPI.
    "ayush.": Section.AYURVEDA,
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
    exact = FIELD_SECTIONS.get(field_id) or BUNDLE_FIELD_SECTIONS.get(field_id)
    if exact is not None:
        return exact
    for prefix in sorted(PREFIX_SECTIONS, key=len, reverse=True):
        if field_id.startswith(prefix):
            return PREFIX_SECTIONS[prefix]
    return DEFAULT_SECTION
