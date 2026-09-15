"""Bounded protocol-2 application journeys using synthetic, encrypted encounters."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_offline_workflow import Driver, receive
from test_offline_workflow import settings as _settings  # noqa: F401

from medikiosk.clinical.translations import prompt as prompt_text
from medikiosk.app import _is_yes, create_app
from medikiosk.clinical.questions import QUESTIONS
from medikiosk.kiosk import ayurveda


def test_health_reports_demo_fallbacks(settings):
    with TestClient(create_app(settings)) as client:
        payload = client.get("/health").json()
        assert payload["status"] == "ok"
        assert payload["openai"]["configured"] is False
        assert payload["sarvam"]["configured"] is False


def test_demo_turn_runs_without_cloud_keys(settings):
    with TestClient(create_app(settings)) as client:
        result = client.post(
            "/api/demo-turn",
            json={"transcript": "I have stomach pain and vomiting", "language": "en-IN"},
        )
        assert result.status_code == 200
        assert result.json()["state"]["complaint"] == "abdominal pain"
        assert result.json()["state"]["vomiting"] is True


def test_demo_turn_triggers_deterministic_chest_pain_emergency(settings):
    with TestClient(create_app(settings)) as client:
        result = client.post(
            "/api/demo-turn",
            json={"transcript": "I have chest pain and I am short of breath", "language": "en-IN"},
        ).json()
        assert result["state"]["breathlessness"] is True
        assert result["should_alert_staff"] is True
        assert result["next_question"] is None


def test_ws_session_binds_a_bare_answer_to_the_question_it_was_asked(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        assert driver.turn("chest pain")["next_question_id"] == "ask_duration"
        second = driver.turn("three days")
        assert second["state"]["duration"] == "three days"
        assert second["next_question_id"] == "ask_severity"
        third = driver.turn("seven")
        assert third["state"]["severity"] == 7
        assert third["next_question_id"] != "ask_severity"


def complete_interview(driver):
    driver.turn("stomach pain")
    for answer in ("three days", "four", "no", "no", "no", "no", "I am 40"):
        result = driver.turn(answer)
        if result["next_question_id"] is None:
            return
    pytest.fail("Interview did not complete within the expected answers")


def test_ws_session_hands_off_when_interview_ends(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        complete_interview(driver)
        assert driver.screen["stage"] == "ayurveda"


def test_ws_drives_the_full_kiosk_workflow(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical", abha="12-3456-7890-1234")
        complete_interview(driver)
        for index, question in enumerate(ayurveda.QUESTIONS, 1):
            assert driver.screen["question_id"] == question.id
            assert driver.screen["progress"] == [index, len(ayurveda.QUESTIONS)]
            driver.act("choose", driver.screen["options"][0]["value"])
        assert driver.screen["gate"] is True
        driver.act("choose", "yes")
        assert driver.screen["stage"] == "consent"
        driver.act("choose", "no")
        assert driver.screen["stage"] == "review"
        driver.act("confirm")
        report = driver.report
        assert report["completion"] == "saved_local"
        assert report["routing"]["queue"] == "Gastroenterology"
        assert report["patient"]["abha_last4"] == "1234"
        assert report["patient"]["reported_by"] == "self"
        assert report["clinical"]["complaint"] == "abdominal pain"
        assert report["ayurveda"]["answered"] == len(ayurveda.QUESTIONS)
        assert report["documents"] == []
        assert "12345678901234" not in str(report)
        ws.send_json(driver.envelope("answer", "new patient"))
        assert driver.until("flow.ack")["type"] == "error"


def test_ws_red_flag_jumps_straight_to_emergency_and_still_reports(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        driver.turn("I have chest pain and I am short of breath")
        assert driver.report["routing"]["queue"] == "Emergency"
        assert driver.report["routing"]["priority"] == "emergency"
        assert driver.report["red_flags"][0]["rule_id"] == "RF_CHEST_PAIN_ASSOCIATED"
        assert driver.screen["stage"] == "emergency"


def test_speech_before_consent_is_not_a_clinical_answer(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        ws.send_json({"type": "transcript.submit", "text": "Namaste", "language": "en-IN"})
        assert driver.until("error")["stage"] == "protocol"
        ws.send_json(driver.envelope("answer", "Namaste"))
        assert driver.until("error")["stage"] == "flow"
        driver.reach_service("clinical", language="hi")
        assert driver.question == "ask_complaint"
        assert not any(e["type"] == "clinical.turn" for e in driver.events)


def test_entering_interview_asks_in_chosen_language(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical", language="hi")
        asked = next(e for e in reversed(driver.events) if e["type"] == "clinical.question")
        assert asked["id"] == "ask_complaint"
        # The opening question is the open "describe your problem" prompt, in the chosen language.
        assert asked["text"] == prompt_text("narrative", "hi")
        assert asked["accumulate"] is True
        assert asked["text"] != QUESTIONS["ask_complaint"].template_for("en")


def test_dropped_connection_resumes_with_secret_capability(settings):
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/session") as ws:
            driver = Driver(ws)
            driver.reach_service("clinical")
            driver.turn("chest pain")
            token, session_id = driver.token, driver.session_id
        with client.websocket_connect(
            "/ws/session", subprotocols=["medikiosk.v2", f"resume.{token}"]
        ) as ws:
            resumed = Driver(ws)
            assert resumed.session_id == session_id
            assert resumed.screen["stage"] == "interview"
            assert resumed.question == "ask_duration"


@pytest.mark.parametrize(
    "query,protocols,code",
    [
        ("?resume=public-session-id", [], 4400),
        ("", ["medikiosk.v2", "resume." + "x" * 43], 4404),
    ],
)
def test_invalid_resume_does_not_silently_start_a_new_patient(settings, query, protocols, code):
    with TestClient(create_app(settings)) as client:
        with (
            pytest.raises(WebSocketDisconnect) as closed,
            client.websocket_connect("/ws/session" + query, subprotocols=protocols) as ws,
        ):
            receive(ws)
        assert closed.value.code == code


def test_ocr_extraction_structures_medications():
    from medikiosk.kiosk import extraction

    result = extraction.extract(["Tab Augmentin 625 mg BD x 5 days"])
    assert result["medications"][0]["strength"] == "625 mg"


def test_unanswerable_question_is_not_repeated_forever(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        seen = []
        for _ in range(30):
            result = driver.turn("unclear synthetic answer")
            seen.append(result["next_question_id"])
            if result["next_question_id"] is None:
                break
        assert seen[-1] is None
        assert max(seen.count(q) for q in set(seen) if q) <= settings.max_question_attempts


def test_confirmation_is_explicit_and_not_a_substring():
    for word in ("yes", "हाँ", "ஆம்", "that is correct", "haan"):
        assert _is_yes(word)
    for word in ("no", "नहीं", "yes but do not save", "not sure"):
        assert not _is_yes(word)


def test_typed_clinical_answers_do_not_require_voice_readback(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        result = driver.turn("chest pain")
        assert result["state"]["complaint"] == "chest pain"
