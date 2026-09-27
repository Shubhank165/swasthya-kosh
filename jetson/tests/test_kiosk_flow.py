
from medikiosk.kiosk import report
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


def test_flow_walks_the_steps_in_order() -> None:
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
    assert flow.stage is Stage.DOCUMENTS
    flow.advance()
    assert flow.stage is Stage.REPORT


def test_red_flag_short_circuits_from_any_stage() -> None:
    """A patient describing an emergency must not be walked through four more screens first.
    This is the whole reason the flow checks flags on every turn."""

    flow = KioskFlow()
    run_to(flow, Stage.INTERVIEW)
    flow.advance()
    assert flow.stage is Stage.DOCUMENTS

    assert flow.check_red_flags([EMERGENCY_FLAG]) is True
    assert flow.stage is Stage.EMERGENCY
    # Terminal: nothing resumes the intake afterwards.
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
