import io
import wave

import pytest

from medikiosk.edge.runtime import pcm_to_wav
from medikiosk.edge.vad import FRAME_BYTES, SpeechSegmenter
from medikiosk.providers.whisper_provider import WhisperCppSTT

FRAME = b"\x01\x00" * (FRAME_BYTES // 2)


def feed(segmenter: SpeechSegmenter, probabilities: list[float]) -> list[bytes]:
    return [u for p in probabilities if (u := segmenter.feed(p, FRAME)) is not None]


def test_segmenter_needs_sustained_speech_to_trigger():
    segmenter = SpeechSegmenter(start_ms=160, frame_ms=32)  # five frames
    feed(segmenter, [0.9] * 4)
    assert not segmenter.triggered
    feed(segmenter, [0.9])
    assert segmenter.triggered


def test_segmenter_emits_utterance_after_trailing_silence():
    segmenter = SpeechSegmenter(start_ms=64, silence_ms=192, frame_ms=32)
    assert feed(segmenter, [0.9] * 10 + [0.0] * 5) == []
    utterances = feed(segmenter, [0.0])
    assert len(utterances) == 1
    # Speech frames plus pre-roll, and nothing left armed for the next turn.
    assert len(utterances[0]) >= 10 * FRAME_BYTES
    assert not segmenter.triggered


def test_segmenter_caps_runaway_utterance():
    segmenter = SpeechSegmenter(start_ms=64, silence_ms=10_000, max_utterance_s=0.32, frame_ms=32)
    utterances = feed(segmenter, [0.9] * 40)
    assert utterances  # continuous speech is cut into capped chunks, never held open
    assert all(len(u) <= 12 * FRAME_BYTES for u in utterances)


def test_segmenter_preroll_keeps_speech_onset():
    segmenter = SpeechSegmenter(start_ms=64, silence_ms=64, pre_roll_ms=128, frame_ms=32)
    utterances = feed(segmenter, [0.0] * 6 + [0.9] * 4 + [0.0] * 2)
    assert len(utterances) == 1
    # Two trigger frames arrive as pre-roll, so the utterance is longer than the frames after it.
    assert len(utterances[0]) > 4 * FRAME_BYTES


def test_pcm_to_wav_round_trip():
    pcm = b"\x00\x01" * 1600
    with wave.open(io.BytesIO(pcm_to_wav(pcm))) as handle:
        assert handle.getframerate() == 16000
        assert handle.getnchannels() == 1
        assert handle.readframes(handle.getnframes()) == pcm


def test_speech_provider_rejects_unsupported_languages():
    speech = WhisperCppSTT()
    with pytest.raises(ValueError):
        speech.transcribe(b"", "fr")  # the kiosk only claims the nine languages it can speak back


def test_voice_bank_reports_missing_voices_instead_of_guessing():
    from medikiosk.providers.voices import VoiceBank

    bank = VoiceBank("nowhere/piper", "nowhere", "nowhere/flite", "nowhere")
    assert bank.missing(["hi", "en"]) == ["hi", "en"]
    assert not bank.available("fr")


def test_direct_answer_binds_yes_no_to_asked_field():
    from medikiosk.clinical.answers import direct_answer
    from medikiosk.clinical.questions import QUESTIONS

    assert direct_answer(QUESTIONS["ask_breathlessness"], "हाँ", "hi") == {"breathlessness": True}
    assert direct_answer(QUESTIONS["ask_breathlessness"], "नहीं", "hi") == {"breathlessness": False}
    assert direct_answer(QUESTIONS["ask_vomiting"], "ஆம்", "ta") == {"vomiting": True}
    assert direct_answer(QUESTIONS["ask_vomiting"], "ಇಲ್ಲ", "kn") == {"vomiting": False}
    # English answers are accepted in every language, because patients code-mix.
    assert direct_answer(QUESTIONS["ask_vomiting"], "yes", "te") == {"vomiting": True}
    # "I don't know" is not a denial.
    assert direct_answer(QUESTIONS["ask_vomiting"], "पता नहीं", "hi") == {}


def test_direct_answer_parses_spoken_numbers_and_keeps_free_text():
    from medikiosk.clinical.answers import direct_answer
    from medikiosk.clinical.questions import QUESTIONS

    assert direct_answer(QUESTIONS["ask_severity"], "सात", "hi") == {"severity": 7}
    assert direct_answer(QUESTIONS["ask_severity"], "ஏழு", "ta") == {"severity": 7}
    assert direct_answer(QUESTIONS["ask_severity"], "बीस", "hi") == {}  # out of the 0-10 scale
    assert direct_answer(QUESTIONS["ask_age"], "पैंतालीस साल", "hi") == {}  # unknown, not a guess
    assert direct_answer(QUESTIONS["ask_age"], "45", "hi") == {"age_years": 45}
    # Duration keeps the patient's words rather than normalizing them into false precision.
    assert direct_answer(QUESTIONS["ask_duration"], "दो दिन से", "hi") == {"duration": "दो दिन से"}


async def test_session_uses_asked_question_for_bare_answer():
    from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
    from medikiosk.clinical.questions import QUESTIONS, TemplateQuestionNaturalizer
    from medikiosk.session import ClinicalSession

    session = ClinicalSession(HeuristicClinicalExtractor(), TemplateQuestionNaturalizer())
    await session.process_transcript("सीने में दर्द", "hi", asked=QUESTIONS["ask_complaint"])
    result = await session.process_transcript("हाँ", "hi", asked=QUESTIONS["ask_breathlessness"])
    assert session.state.breathlessness is True
    # Chest pain plus breathlessness is a configured emergency rule.
    assert result.should_alert_staff
    assert [flag.rule_id for flag in result.red_flags] == ["RF_CHEST_PAIN_ASSOCIATED"]


def test_state_machine_skips_questions_that_never_resolved():
    from medikiosk.clinical.state_machine import ClinicalStateMachine
    from medikiosk.models import PatientState

    machine = ClinicalStateMachine()
    state = PatientState()
    assert machine.next_question(state).id == "ask_complaint"
    assert machine.next_question(state, {"ask_complaint"}).id == "ask_duration"


async def test_chief_complaint_is_not_replaced_by_a_later_symptom():
    from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
    from medikiosk.clinical.questions import QUESTIONS, TemplateQuestionNaturalizer
    from medikiosk.session import ClinicalSession

    session = ClinicalSession(HeuristicClinicalExtractor(), TemplateQuestionNaturalizer())
    await session.process_transcript("सीने में दर्द", "hi", asked=QUESTIONS["ask_complaint"])
    await session.process_transcript("पेट में दर्द", "hi", asked=QUESTIONS["ask_radiation"])
    assert session.state.complaint == "chest pain"
    assert session.state.original_transcripts[-1] == "पेट में दर्द"  # evidence still kept


def test_every_supported_language_has_complete_text():
    """A missing translation would otherwise surface as English spoken by an Indic voice."""

    from medikiosk.clinical.translations import PROMPT_TEXT, QUESTION_TEXT
    from medikiosk.languages import LANGUAGES

    for question_id, texts in QUESTION_TEXT.items():
        missing = sorted(set(LANGUAGES) - set(texts))
        assert not missing, f"{question_id} missing: {missing}"
    for key, texts in PROMPT_TEXT.items():
        missing = sorted(set(LANGUAGES) - set(texts))
        assert not missing, f"prompt {key} missing: {missing}"


def test_every_question_id_has_text_and_a_state_field():
    from medikiosk.clinical.questions import QUESTIONS, TARGET_FIELD
    from medikiosk.models import PatientState

    state = PatientState()
    for question_id, field in TARGET_FIELD.items():
        assert hasattr(state, field), f"{question_id} targets unknown field {field}"
        assert QUESTIONS[question_id].template_for("en")


def test_language_codes_normalize_to_a_template():
    from medikiosk.clinical.questions import QUESTIONS

    question = QUESTIONS["ask_fever"]
    assert question.template_for("hi") == question.template_for("hi-IN")
    assert question.template_for("hinglish") == question.template_for("hi")
    assert question.template_for("fr") == question.template_for("en")  # unsupported falls back


def test_whisper_output_is_stripped_of_non_speech_annotations():
    from medikiosk.providers.whisper_provider import _strip_annotations

    assert _strip_annotations("[BLANK_AUDIO]") == ""
    assert _strip_annotations(" (music)  सीने में दर्द ") == "सीने में दर्द"
    assert _strip_annotations("chest pain") == "chest pain"


def test_rms_rejects_silence_and_measures_speech():
    """Whisper invents fluent sentences from silence and reports high confidence doing it.

    On pure digital silence the server returned ' you' with no_speech_prob 2e-10, so the model's
    own confidence cannot be the guard. Energy can.
    """

    from medikiosk.edge.runtime import rms

    assert rms(b"") == 0
    assert rms(bytes(16000 * 2)) == 0  # one second of digital silence
    loud = b"".join((6000).to_bytes(2, "little", signed=True) for _ in range(1000))
    assert rms(loud) > 120  # comfortably above the rejection floor


async def test_a_silent_turn_never_becomes_a_clinical_fact():
    """The failure this guards: a hallucinated 'Yes.' from silence raised a false red flag."""

    from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
    from medikiosk.clinical.questions import QUESTIONS, TemplateQuestionNaturalizer
    from medikiosk.session import ClinicalSession

    session = ClinicalSession(HeuristicClinicalExtractor(), TemplateQuestionNaturalizer())
    with pytest.raises(ValueError):
        # An empty transcript must be refused outright, not applied as an answer.
        await session.process_transcript("", "hi", asked=QUESTIONS["ask_breathlessness"])
    assert session.state.breathlessness is None


def test_barge_in_guard_settings_have_safe_defaults():
    """Background conversation barged the kiosk out of every prompt 7 ms in and was recorded as
    the patient's answer. The guard window plus the require-silence rule prevent that."""

    from medikiosk.config import Settings

    settings = Settings()
    assert settings.barge_in_guard_ms >= 500
    # Interrupting must need stronger evidence than a normal turn, or room noise qualifies.
    assert settings.barge_in_threshold > settings.vad_threshold
    assert settings.barge_in_start_ms > settings.vad_start_ms
