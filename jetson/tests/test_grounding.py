"""The LLM proposes, the transcript disposes.

Every case here is a value gemma3:1b actually produced on the Jetson, or the shape of one.
"""

import pytest

from medikiosk.clinical.grounding import (
    ground,
    grounded_age,
    grounded_complaint,
    grounded_duration,
    grounded_list,
    numbers_in,
)
from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
from medikiosk.clinical.hybrid import HybridClinicalExtractor
from medikiosk.models import ClinicalUpdate
from medikiosk.providers.local_llm_provider import EMPTY_UPDATE_KWARGS


def update(**fields) -> ClinicalUpdate:
    return ClinicalUpdate(**{**EMPTY_UPDATE_KWARGS, **fields})


def test_numbers_are_read_in_digits_english_hindi_and_hinglish():
    assert numbers_in("since 5 days") == {5}
    assert numbers_in("paanch din se") == {5}
    assert numbers_in("दो दिन से") == {2}
    assert numbers_in("for two weeks") == {2}
    assert numbers_in("main pachpan saal ka hoon") == {55}
    assert numbers_in("just tired") == set()


@pytest.mark.parametrize(
    "claimed, said, kept",
    [
        # The copied-example failure, verbatim from the Jetson.
        ("two days", "pet me dard hai paanch din se", None),
        ("two days", "pain in lower abdomen since five days", None),
        ("five days", "pain in lower abdomen since five days", "five days"),
        ("five days", "pet me dard hai paanch din se", "five days"),
        ("two days", "मुझे दोदो दी से पेट में दर्द है", "two days"),  # दो is there
        ("three weeks", "मुझे तीन हफ्ते से सिर दर्द है", "three weeks"),
        ("since yesterday", "my ankle hurts since yesterday", "since yesterday"),
        ("since yesterday", "kal se pair me dard", "since yesterday"),
        ("since yesterday", "pet me dard", None),
        ("one week", "sir dard hai", None),
    ],
)
def test_a_duration_must_carry_a_number_the_patient_said(claimed, said, kept):
    assert grounded_duration(claimed, said) == kept


def test_an_age_must_be_a_number_the_patient_said():
    assert grounded_age(55, "main pachpan saal ka hoon") == 55
    assert grounded_age(34, "I am 34 years old") == 34
    assert grounded_age(41, "sugar badh gayi hai") is None


@pytest.mark.parametrize(
    "claimed, said, kept",
    [
        # Body part copied from the prompt example, patient said stomach.
        ("ear pain", "pet me dard hai paanch din se", None),
        ("abdominal pain", "pet me dard hai paanch din se", "abdominal pain"),
        ("lower back pain", "kamar me dard hai", "lower back pain"),
        ("back", "kaan me dard hai teen din se", None),
        ("ear pain", "kaan me dard hai teen din se", "ear pain"),
        ("headache", "मुझे तीन हफ्ते से सिर दर्द है", "headache"),
        ("high blood sugar", "sugar badh gayi hai", "high blood sugar"),
        # Unknown to the lexicon: the model's own word must be in the transcript.
        ("ankle pain", "my ankle hurts since yesterday", "ankle pain"),
        ("ankle pain", "mera pair mud gaya", None),
        ("pain", "pet me dard", None),  # a bare "pain" names nothing
    ],
)
def test_a_complaint_must_name_something_the_patient_mentioned(claimed, said, kept):
    assert grounded_complaint(claimed, said) == kept


def test_symptom_flags_need_the_symptom_to_have_come_up_at_all():
    proposed = update(fever=True, vomiting=True, breathlessness=False, chest_pain=True)
    kept = ground(proposed, "pet me dard hai aur ulti ho rahi hai")
    assert kept.vomiting is True
    assert kept.fever is None, "fever was never mentioned"
    assert kept.breathlessness is None
    assert kept.chest_pain is None
    # A denial mentions the symptom, so it survives.
    assert ground(update(fever=False), "bukhar nahi hai").fever is False


def test_placeholders_and_unmentioned_drugs_are_dropped():
    assert grounded_list(["not specified"], "sir dard") == []
    assert grounded_list(["metformin", "aspirin"], "I take metformin daily") == ["metformin"]


@pytest.mark.asyncio
async def test_the_hybrid_extractor_grounds_the_llm_before_merging():
    class Copycat:
        async def extract(self, transcript):
            # What gemma3:1b returned for "pet me dard hai paanch din se" on the Jetson.
            return update(
                complaint="ear pain", duration="two days", fever=False, evidence=["ear pain"]
            )

    merged = await HybridClinicalExtractor(HeuristicClinicalExtractor(), Copycat()).extract(
        "pet me dard hai paanch din se, ulti bhi ho rahi hai"
    )
    # The deterministic Hinglish match carries the record; the copied values never land.
    assert merged.complaint == "abdominal pain"
    assert merged.duration == "paanch din"
    assert merged.vomiting is True
    assert merged.fever is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "said, complaint, duration",
    [
        ("pet me dard hai paanch din se", "abdominal pain", "paanch din"),
        ("sir dard teen din se", "headache", "teen din"),
        ("kaan mein dard hai do hafte se", "ear pain", "do hafte"),
        ("kamar me dard hai kal se", "back pain", "since yesterday"),
        ("मुझे तीन हफ्ते से सिर दर्द है", "headache", "तीन हफ्ते"),
        ("bukhar hai do din se aur khansi bhi", "cough", "do din"),
        # A body-part complaint outranks a symptom mentioned alongside it (live demo run).
        ("pain in lower abdomen since five days, vomiting, fever", "abdominal pain", "five days"),
    ],
)
async def test_hinglish_reaches_the_deterministic_extractor(said, complaint, duration):
    result = await HeuristicClinicalExtractor().extract(said)
    assert result.complaint == complaint
    assert result.duration == duration
