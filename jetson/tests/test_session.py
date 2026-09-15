import pytest

from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
from medikiosk.clinical.questions import TemplateQuestionNaturalizer
from medikiosk.session import ClinicalSession


@pytest.mark.asyncio
async def test_session_merges_state_and_selects_next_question() -> None:
    session = ClinicalSession(HeuristicClinicalExtractor(), TemplateQuestionNaturalizer())
    result = await session.process_transcript(
        "I have stomach pain for three days and I vomited twice.",
        "en-IN",
    )
    assert result.state.complaint == "abdominal pain"
    assert result.state.duration == "three days"
    assert result.state.vomiting is True
    assert result.next_question_id == "ask_severity"
    assert result.should_alert_staff is False


@pytest.mark.asyncio
async def test_emergency_stops_question_selection() -> None:
    session = ClinicalSession(HeuristicClinicalExtractor(), TemplateQuestionNaturalizer())
    result = await session.process_transcript(
        "I have chest pain and difficulty breathing.",
        "en-IN",
    )
    assert result.should_alert_staff is True
    assert result.next_question is None


@pytest.mark.asyncio
async def test_devanagari_duration_keeps_its_vowel_signs() -> None:
    """Devanagari matras are combining marks, which Python's \b does not treat as word characters.
    A trailing \b therefore matched before the matra and put "दो हफ्त" on the doctor's sheet."""

    extractor = HeuristicClinicalExtractor()
    assert (await extractor.extract("दो हफ्ते")).duration == "दो हफ्ते"
    assert (await extractor.extract("दो हफ्तों से")).duration == "दो हफ्तों"
    assert (await extractor.extract("तीन दिन")).duration == "तीन दिन"
    assert (await extractor.extract("three days.")).duration == "three days"


@pytest.mark.asyncio
async def test_hindi_postposition_does_not_swallow_the_complaint() -> None:
    """से follows its phrase ("दो हफ्ते से"); for/since precede theirs. Treating them alike made
    the duration field capture the complaint text and print it on the doctor's sheet."""

    extractor = HeuristicClinicalExtractor()
    update = await extractor.extract("मुझे दो हफ्ते से पेट में दर्द है")
    assert update.duration == "दो हफ्ते"
    assert update.complaint == "abdominal pain"

    # English prepositions still work the way they always did.
    english = await extractor.extract("I have had stomach pain for three days")
    assert english.duration == "three days"
