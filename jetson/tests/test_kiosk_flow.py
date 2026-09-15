import pytest

from medikiosk.kiosk import ayurveda, prakriti, report
from medikiosk.kiosk.abha import VisitRecords, from_qr_payload, normalise
from medikiosk.kiosk.flow import SCREEN_TEXT, KioskFlow, Stage
from medikiosk.languages import LANGUAGES
from medikiosk.models import PatientState, RedFlagAlert, Urgency

EMERGENCY_FLAG = RedFlagAlert(
    rule_id="RF_CHEST_PAIN_ASSOCIATED",
    urgency=Urgency.EMERGENCY,
    message="Chest pain with an associated warning symptom.",
    evidence=["chest_pain=true"],
)


def run_to(flow: KioskFlow, stage: Stage) -> KioskFlow:
    """Walk the flow forward to a given stage the way a patient would."""

    flow.choose_language("hi")
    if stage is Stage.ABHA:
        return flow
    flow.set_abha(None)
    if stage is Stage.WHO:
        return flow
    flow.set_who("self")
    return flow


def test_every_screen_line_exists_in_every_language() -> None:
    """A missing translation is invisible: flow.text() silently returns the English line.

    That silence is the whole bug this guards. Seven of the nine languages had no screen text at
    all, so a Tamil patient was shown - and, because the pre-render gives an untranslated line the
    English voice, read aloud - English for every prompt outside the clinical questions. Nothing
    failed; it just quietly stopped being a Tamil kiosk.
    """

    missing = {
        key: sorted(set(LANGUAGES) - set(entry))
        for key, entry in SCREEN_TEXT.items()
        if set(LANGUAGES) - set(entry)
    }
    assert missing == {}, f"screen text falls back to English for: {missing}"


def test_screen_text_is_not_english_copied_into_every_slot() -> None:
    """Filling the slots with the English string would pass the test above and fix nothing."""

    for key, entry in SCREEN_TEXT.items():
        for language in ("hi", "ta", "bn", "kn"):
            assert entry[language] != entry["en"], f"{key}/{language} is still the English line"


def test_flow_walks_the_nine_steps_in_order() -> None:
    flow = KioskFlow()
    assert flow.stage is Stage.LANGUAGE
    flow.choose_language("hi")
    assert flow.stage is Stage.ABHA
    flow.set_abha("12345678901234", history=[{"recorded_at": "2026-01-01T00:00:00Z"}])
    assert flow.stage is Stage.WHO
    flow.set_who("other")
    assert flow.on_behalf_of == "other"
    assert flow.stage is Stage.INTERVIEW
    flow.advance()
    assert flow.stage is Stage.AYURVEDA
    for question in ayurveda.QUESTIONS:
        flow.answer_ayurveda(question.id, question.options[0].value)
    # Prakriti sits between the Ayurvedic questions and the documents, and opens by asking whether
    # the patient has ever filled it - it is once in a lifetime, not once a visit.
    assert flow.stage is Stage.PRAKRITI
    assert flow.answer_prakriti_gate("yes") is True
    assert flow.stage is Stage.DOCUMENTS
    flow.advance()
    assert flow.stage is Stage.REPORT


def test_ayush_track_off_skips_the_questionnaire() -> None:
    """Dashavidha is skipped, but Prakriti is not - it is asked of everyone, once."""

    flow = KioskFlow(ayush_track=False)
    run_to(flow, Stage.INTERVIEW)
    flow.advance()
    assert flow.stage is Stage.PRAKRITI
    flow.answer_prakriti_gate("yes")
    assert flow.stage is Stage.DOCUMENTS


def test_a_known_prakriti_skips_the_stage_entirely() -> None:
    """A patient whose constitution is already on record is never asked the 58 questions again."""

    flow = KioskFlow(ayush_track=False)
    flow.choose_language("hi")
    flow.load_prakriti({"prakriti": "Kaphaja", "recorded_at": "2025-03-04T00:00:00Z"})
    flow.set_abha("12345678901234")
    flow.set_who("self")
    assert flow.needs_prakriti is False
    flow.advance()
    assert flow.stage is Stage.DOCUMENTS


def test_answering_the_questionnaire_produces_a_prakriti() -> None:
    flow = KioskFlow(ayush_track=False)
    run_to(flow, Stage.INTERVIEW)
    flow.advance()
    assert flow.answer_prakriti_gate("no") is False
    assert flow.stage is Stage.PRAKRITI

    finished = False
    while (item := prakriti.next_item(flow.prakriti_answers)) is not None:
        # Kapha where the item offers it, otherwise an answer that scores nothing - picking
        # choices[0] blindly would smuggle in Vata marks and produce a dual Prakriti.
        choice = next(
            (c for c in item.choices if c.dosha == "kapha"),
            next((c for c in item.choices if c.dosha is None), item.choices[0]),
        )
        finished = flow.answer_prakriti(item.id, choice.value)
    assert finished is True
    assert flow.stage is Stage.DOCUMENTS
    assert flow.prakriti_record is not None
    assert flow.prakriti_record["prakriti"] == "Kaphaja"
    # Never presented as the certified CCRAS result - the weights have not been reviewed.
    assert flow.prakriti_record["scoring_reviewed"] is False


def test_prakriti_rejects_an_answer_the_form_does_not_offer() -> None:
    flow = KioskFlow(ayush_track=False)
    run_to(flow, Stage.INTERVIEW)
    flow.advance()
    flow.answer_prakriti_gate("no")
    with pytest.raises(ValueError):
        flow.answer_prakriti("pk_sleep_hours", "twelve")
    with pytest.raises(ValueError):
        flow.answer_prakriti("pk_not_a_question", "yes")
    with pytest.raises(ValueError):
        flow.answer_prakriti_gate("maybe")


def test_red_flag_short_circuits_from_any_stage() -> None:
    """A patient describing an emergency during the Ayurvedic questions must not be walked through
    four more screens first. This is the whole reason the flow checks flags on every turn."""

    flow = KioskFlow()
    run_to(flow, Stage.INTERVIEW)
    flow.advance()
    assert flow.stage is Stage.AYURVEDA

    assert flow.check_red_flags([EMERGENCY_FLAG]) is True
    assert flow.stage is Stage.EMERGENCY
    # Terminal: nothing resumes the questionnaire afterwards.
    assert flow.advance() is Stage.EMERGENCY
    assert flow.screen(PatientState())["alert"] is True


def test_emergency_still_produces_a_report_for_staff() -> None:
    flow = KioskFlow()
    run_to(flow, Stage.INTERVIEW)
    flow.raise_emergency()
    state = PatientState(complaint="chest pain", breathlessness=True)
    built = flow.finish(state, [EMERGENCY_FLAG])
    assert built["routing"]["queue"] == "Emergency"
    assert built["routing"]["priority"] == "emergency"


def test_rejects_unknown_questionnaire_answers() -> None:
    flow = KioskFlow()
    with pytest.raises(ValueError):
        flow.answer_ayurveda("ayu_build", "not-an-option")
    with pytest.raises(ValueError):
        flow.answer_ayurveda("no_such_question", "thin")


def test_routing_sends_complaints_to_the_right_queue() -> None:
    cases = {
        "chest pain": "Cardiology",
        "ankle pain": "Orthopaedics",
        "ear pain": "ENT",
        "पेट में दर्द": "Gastroenterology",
        "something nobody listed": "General Medicine",
    }
    for complaint, expected in cases.items():
        routed = report.route(PatientState(complaint=complaint), [])
        assert routed["queue"] == expected, complaint


def test_questionnaire_alone_does_not_divert_the_specialist_queue() -> None:
    """Answering the Dashavidha questions is not a request for a vaidya. Conflating the two sent
    every patient to Ayush OPD regardless of complaint - a knee went there instead of Orthopaedics."""

    flow = KioskFlow(ayush_track=True)
    run_to(flow, Stage.INTERVIEW)
    for question in ayurveda.QUESTIONS:
        flow.answer_ayurveda(question.id, question.options[0].value)
    built = flow.finish(PatientState(complaint="knee pain"), [])
    assert built["routing"]["queue"] == "Orthopaedics"
    assert built["ayurveda"]["answered"] == len(ayurveda.QUESTIONS)

    chose = KioskFlow(prefers_ayush=True)
    routed = report.route(PatientState(complaint="knee pain"), [], prefers_ayush=chose.prefers_ayush)
    assert routed["queue"] == "Ayush OPD"
    assert routed["also_indicated"] == "Orthopaedics"


def test_emergency_outranks_the_ayush_track() -> None:
    """An Ayurvedic consultation request must never divert a patient away from Emergency."""

    routed = report.route(PatientState(complaint="chest pain"), [EMERGENCY_FLAG], prefers_ayush=True)
    assert routed["queue"] == "Emergency"


def test_constitution_is_not_named_without_enough_answers() -> None:
    """A confident Prakriti on a doctor's sheet from two answers would be a fabrication."""

    assert ayurveda.summarize({"ayu_build": "thin"})["prakriti_tendency"] is None
    leaning = ayurveda.summarize(
        {"ayu_build": "thin", "ayu_skin": "dry", "ayu_sleep": "light", "ayu_weather": "cold"}
    )
    assert leaning["prakriti_tendency"] == "vata"
    tied = ayurveda.summarize(
        {"ayu_build": "thin", "ayu_skin": "dry", "ayu_sleep": "deep", "ayu_weather": "damp"}
    )
    assert "-" in tied["prakriti_tendency"]


def test_report_lists_what_the_kiosk_could_not_establish() -> None:
    built = report.build(PatientState(complaint="headache"), [])
    assert "severity" in built["clinical"]["not_established"]
    assert built["patient"]["abha_last4"] is None


def test_report_shows_only_the_last_four_abha_digits() -> None:
    built = report.build(PatientState(), [], abha_number="12345678901234")
    assert built["patient"]["abha_last4"] == "1234"
    assert "12345678901234" not in str(built)


def test_abha_number_parsing() -> None:
    assert normalise("12-3456-7890-1234") == "12345678901234"
    assert normalise("123") is None
    assert from_qr_payload('{"hidn": "12345678901234"}') == "12345678901234"
    assert from_qr_payload("12-3456-7890-1234") == "12345678901234"
    assert from_qr_payload("not a card") is None


def test_visit_history_round_trips_without_storing_the_number(tmp_path) -> None:
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("ascii")
    store = VisitRecords(tmp_path / "visits.db", key)
    store.save("12345678901234", {"complaint": "chest pain", "recorded_at": "2026-01-01T00:00:00Z"})
    store.save("12345678901234", {"complaint": "headache", "recorded_at": "2026-02-01T00:00:00Z"})
    store.save("99999999999999", {"complaint": "other patient"})

    history = store.history("12345678901234")
    assert [visit["complaint"] for visit in history] == ["headache", "chest pain"]
    assert store.history("00000000000000") == []

    raw = (tmp_path / "visits.db").read_bytes()
    assert b"12345678901234" not in raw, "ABHA number must not be stored in the clear"
    assert b"chest pain" not in raw, "complaint must not be stored in the clear"


def test_back_undoes_the_stage_it_returns_to() -> None:
    """A mistapped language or ABHA number must be correctable. Going back has to clear the answer
    it is returning to collect, or the flow steps straight over it again."""

    flow = KioskFlow()
    flow.choose_language("hi")
    flow.set_abha("12345678901234", history=[{"recorded_at": "2026-01-01T00:00:00Z"}])
    assert flow.stage is Stage.WHO

    assert flow.back() is Stage.ABHA
    assert flow.abha_number is None, "returning to the ABHA screen must clear the old number"
    assert flow.past_visits == []

    flow.set_abha(None)
    flow.set_who("other")
    assert flow.back() is Stage.WHO
    assert flow.on_behalf_of is None

    # Language is the first stage; there is nowhere further back to go.
    flow.stage = Stage.LANGUAGE
    assert flow.back() is Stage.LANGUAGE


def test_back_is_refused_during_an_emergency() -> None:
    """Nothing navigates away from an emergency screen."""

    flow = KioskFlow()
    run_to(flow, Stage.INTERVIEW)
    flow.raise_emergency()
    assert flow.back() is Stage.EMERGENCY
