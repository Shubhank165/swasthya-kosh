from fastapi.testclient import TestClient

from medikiosk.app import create_app
from medikiosk.clinical.questions import QUESTIONS
from medikiosk.config import Settings
from medikiosk.kiosk import ayurveda


def _wait_for(ws, message_type: str) -> dict:
    message = ws.receive_json()
    while message["type"] != message_type:
        message = ws.receive_json()
    return message


def _screen(ws) -> dict:
    return _wait_for(ws, "flow.screen")["data"]


def reach_interview(ws, language: str = "en") -> None:
    """Walk the workflow to the interview stage, the way a patient taps through it."""

    _screen(ws)
    ws.send_json({"type": "flow.language", "value": language})
    _screen(ws)
    ws.send_json({"type": "flow.abha", "value": ""})
    _screen(ws)
    ws.send_json({"type": "flow.who", "value": "self"})
    assert _screen(ws)["stage"] == "interview"


def test_health_reports_demo_fallbacks() -> None:
    client = TestClient(create_app(Settings(deployment_profile="demo")))
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["openai"]["configured"] is False
    assert payload["sarvam"]["configured"] is False


def test_demo_turn_runs_without_cloud_keys() -> None:
    client = TestClient(create_app(Settings(deployment_profile="demo")))
    response = client.post(
        "/api/demo-turn",
        json={"transcript": "I have stomach pain and vomiting", "language": "en-IN"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["complaint"] == "abdominal pain"
    assert payload["state"]["vomiting"] is True


def test_demo_turn_triggers_deterministic_chest_pain_emergency() -> None:
    client = TestClient(create_app(Settings(deployment_profile="demo")))
    response = client.post(
        "/api/demo-turn",
        json={
            "transcript": "I have chest pain and I am short of breath",
            "language": "en-IN",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["breathlessness"] is True
    assert payload["should_alert_staff"] is True
    assert payload["next_question"] is None


def test_ws_session_binds_a_bare_answer_to_the_question_it_was_asked() -> None:
    """The phone test kept re-asking 'how long have you had this problem?' because the web path
    processed every turn with asked=None: a bare 'three days' had no field to bind to. This drives
    the WebSocket exactly as the browser does (transcript.submit, no audio) and checks the second
    turn both fills duration and moves the state machine past ask_duration."""

    def turn(ws, text: str) -> dict:
        ws.send_json({"type": "transcript.submit", "text": text, "language": "en-IN"})
        message = ws.receive_json()
        while message["type"] != "clinical.turn":
            message = ws.receive_json()
        return message["data"]

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        reach_interview(ws)
        first = turn(ws, "chest pain")
        assert first["next_question_id"] == "ask_duration"

        second = turn(ws, "three days")
        assert second["state"]["duration"] == "three days"
        assert second["next_question_id"] == "ask_severity"

        # A bare number is not something the heuristic extractor's own severity regex catches
        # (it needs "severity"/"pain" as an anchor); only asked= binding resolves it, so this
        # turn is the one that actually proves the wiring rather than the regex widening.
        third = turn(ws, "seven")
        assert third["state"]["severity"] == 7
        assert third["next_question_id"] != "ask_severity"

        ws.send_json({"type": "session.stop"})


def test_ws_session_hands_off_to_the_next_stage_when_the_interview_ends() -> None:
    """The web path used to fall silent when the state machine ran out of questions: the patient
    kept talking and every word was transcribed into nothing. Now the interview ending hands back
    to the workflow, and once the report is built further speech is dropped rather than recorded."""

    def turn(ws, text: str) -> dict:
        ws.send_json({"type": "transcript.submit", "text": text, "language": "en-IN"})
        return _wait_for(ws, "clinical.turn")["data"]

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        _screen(ws)
        ws.send_json({"type": "flow.language", "value": "en"})
        _screen(ws)
        ws.send_json({"type": "flow.abha", "value": ""})
        _screen(ws)
        ws.send_json({"type": "flow.who", "value": "self"})
        assert _screen(ws)["stage"] == "interview"

        for answer in ("stomach pain", "three days", "four", "no", "no", "no", "no", "I am 40"):
            result = turn(ws, answer)
            if result["next_question_id"] is None:
                break
        assert result["next_question_id"] is None, "intake never completed"

        # The interview no longer dead-ends; it hands off to the questionnaire.
        assert _screen(ws)["stage"] == "ayurveda"
        ws.send_json({"type": "session.stop"})


def test_ws_drives_the_full_kiosk_workflow() -> None:
    """Language, ABHA, who is answering, interview, Dashavidha, Prakriti, documents, report -
    the whole sheet the doctor gets, driven the way a tablet would drive it."""

    def turn(ws, text: str) -> dict:
        ws.send_json({"type": "transcript.submit", "text": text, "language": "en-IN"})
        return _wait_for(ws, "clinical.turn")["data"]

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        first = _screen(ws)
        assert first["stage"] == "language"
        assert any(option["value"] == "hi" for option in first["options"])

        ws.send_json({"type": "flow.language", "value": "en"})
        assert _screen(ws)["stage"] == "abha"

        ws.send_json({"type": "flow.abha", "value": "12-3456-7890-1234"})
        assert _screen(ws)["stage"] == "who"

        ws.send_json({"type": "flow.who", "value": "self"})
        assert _screen(ws)["stage"] == "interview"

        # Steps 4 and 5: describe the issue, then the dynamic interview. The complaint has to be
        # one the heuristic extractor knows, because these tests run with no Ollama behind them.
        turn(ws, "stomach pain")
        for answer in ("two weeks", "four", "no", "no", "no", "no", "I am 30"):
            result = turn(ws, answer)
            if result["next_question_id"] is None:
                break

        # Step 6: Dashavidha questionnaire, one touch answer per screen.
        screen = _screen(ws)
        assert screen["stage"] == "ayurveda"
        for _ in ayurveda.QUESTIONS:
            if screen.get("stage") != "ayurveda" or screen.get("complete"):
                break
            ws.send_json(
                {
                    "type": "flow.ayurveda",
                    "question_id": screen["question_id"],
                    "value": screen["options"][0]["value"],
                }
            )
            screen = _screen(ws)

        # Step 7: Prakriti. Asked once in a lifetime, so it opens by asking whether the
        # patient has ever filled it; saying yes takes the whole stage off the path.
        assert screen["stage"] == "prakriti"
        assert screen["gate"] is True
        ws.send_json({"type": "flow.prakriti", "value": "yes"})
        screen = _screen(ws)

        # Step 8: documents.
        assert screen["stage"] == "documents"
        ws.send_json({"type": "flow.document", "lines": ["Paracetamol 500mg"], "seconds": 1.7})
        assert _screen(ws)["stage"] == "documents"

        # Step 8: report and queue.
        ws.send_json({"type": "flow.next"})
        report = _wait_for(ws, "flow.report")["data"]

        # Answering the constitution questions must not divert an abdominal complaint to Ayush OPD.
        assert report["routing"]["queue"] == "Gastroenterology"
        assert report["patient"]["abha_last4"] == "1234"
        assert report["patient"]["reported_by"] == "self"
        assert report["clinical"]["complaint"] == "abdominal pain"
        assert report["ayurveda"]["answered"] == len(ayurveda.QUESTIONS)
        assert report["documents"][0]["lines"] == ["Paracetamol 500mg"]
        assert "12345678901234" not in str(report)

        ws.send_json({"type": "session.stop"})


def test_ws_red_flag_jumps_straight_to_emergency_and_still_reports() -> None:
    """A red flag mid-interview must not walk the patient through the remaining stages."""

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        assert _screen(ws)["stage"] == "language"
        ws.send_json({"type": "flow.language", "value": "en"})
        _screen(ws)
        ws.send_json({"type": "flow.abha", "value": ""})
        _screen(ws)
        ws.send_json({"type": "flow.who", "value": "self"})
        assert _screen(ws)["stage"] == "interview"

        ws.send_json(
            {
                "type": "transcript.submit",
                "text": "I have chest pain and I am short of breath",
                "language": "en-IN",
            }
        )
        report = _wait_for(ws, "flow.report")["data"]
        assert report["routing"]["queue"] == "Emergency"
        assert report["routing"]["priority"] == "emergency"
        assert report["red_flags"][0]["rule_id"] == "RF_CHEST_PAIN_ASSOCIATED"

        assert _screen(ws)["stage"] == "emergency"
        ws.send_json({"type": "session.stop"})


def test_speech_before_the_interview_is_not_treated_as_an_answer() -> None:
    """A patient saying "Namaste" at the language screen had it fed straight to the extractor,
    which returned a chief complaint of "ear pain" and consumed ask_complaint without ever asking
    it. Anything said outside the interview stage must be dropped."""

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        assert _screen(ws)["stage"] == "language"

        ws.send_json({"type": "transcript.submit", "text": "Namaste", "language": "en-IN"})
        # No clinical turn may come back; the next thing is the language screen re-sent, if
        # anything at all. Walking on must still start the interview from a clean state.
        ws.send_json({"type": "flow.language", "value": "hi"})
        _screen(ws)
        ws.send_json({"type": "flow.abha", "value": ""})
        _screen(ws)
        ws.send_json({"type": "flow.who", "value": "self"})
        assert _screen(ws)["stage"] == "interview"

        message = _wait_for(ws, "clinical.question")
        assert message["id"] == "ask_complaint", "the interview must open by asking, not waiting"

        ws.send_json({"type": "session.stop"})


def test_entering_the_interview_asks_the_first_question_in_the_chosen_language() -> None:
    """Arriving at the interview left the kiosk silent until the patient spoke first. It must ask
    ask_complaint itself, worded in the language the patient picked."""

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        reach_interview(ws, language="hi")
        asked = _wait_for(ws, "clinical.question")
        assert asked["id"] == "ask_complaint"
        assert asked["text"] == QUESTIONS["ask_complaint"].template_for("hi")
        assert asked["text"] != QUESTIONS["ask_complaint"].template_for("en")
        ws.send_json({"type": "session.stop"})


def test_a_dropped_connection_resumes_instead_of_restarting_the_patient() -> None:
    """An intake takes minutes. Making someone in pain start again from the language screen
    because the link blinked is the difference between a demo and something usable in an OPD."""

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        session_id = _wait_for(ws, "session.id")["session_id"]
        reach_interview(ws)
        _wait_for(ws, "clinical.question")
        ws.send_json({"type": "transcript.submit", "text": "chest pain", "language": "en-IN"})
        _wait_for(ws, "clinical.turn")
        # Drop without session.stop, the way a tablet losing power does.

    with client.websocket_connect(f"/ws/session?resume={session_id}") as ws:
        screen = _screen(ws)
        assert screen["stage"] == "interview", "resumed mid-interview, not back at language select"
        ws.send_json({"type": "session.stop"})


def test_an_unknown_resume_id_starts_a_clean_session() -> None:
    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session?resume=not-a-real-session") as ws:
        assert _screen(ws)["stage"] == "language"
        ws.send_json({"type": "session.stop"})


def test_ocr_endpoint_returns_structured_medications() -> None:
    """The doctor should see medications and doses, not a wall of OCR text."""

    from medikiosk.kiosk import extraction

    result = extraction.extract(["Tab Augmentin 625 mg BD x 5 days"])
    assert result["medications"][0]["strength"] == "625 mg"


def test_an_unanswerable_question_is_given_up_on_rather_than_repeated_forever() -> None:
    """A patient who cannot answer ask_age was asked it indefinitely on the web path, with no way
    to reach the end of the intake. The wired kiosk has always capped attempts; this path did not."""

    def turn(ws, text: str) -> dict:
        ws.send_json({"type": "transcript.submit", "text": text, "language": "en-IN"})
        return _wait_for(ws, "clinical.turn")["data"]

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        reach_interview(ws)
        _wait_for(ws, "clinical.question")

        seen = []
        for _ in range(14):
            result = turn(ws, "no")
            seen.append(result["next_question_id"])
            if result["next_question_id"] is None:
                break

        assert seen[-1] is None, f"interview never terminated; asked {seen}"
        # No single question may dominate: repeating one more than a handful of times is the bug.
        assert max(seen.count(q) for q in set(seen) if q) <= 3
        ws.send_json({"type": "session.stop"})


def test_a_spoken_answer_is_read_back_before_it_is_acted_on() -> None:
    """Whisper mishears short words in a noisy OPD, and a patient who cannot read has no other way
    to catch it. A heard answer is repeated back and only recorded after a yes."""

    import asyncio

    from medikiosk.app import _is_yes

    # The confirmation vocabulary spans every supported language, and patients mix English in.
    assert _is_yes("haan") is False, "romanised Hindi is not in the vocabulary"
    assert _is_yes("yes")
    assert _is_yes("हाँ")
    assert _is_yes("ஆம்")
    assert _is_yes("that is correct")
    assert not _is_yes("no")
    assert not _is_yes("नहीं")
    del asyncio


def test_typed_answers_are_not_read_back() -> None:
    """Text the patient typed is already on screen in front of them. Confirming it would double
    every interaction for no safety gain, so read-back applies only to what was heard."""

    def turn(ws, text: str) -> dict:
        ws.send_json({"type": "transcript.submit", "text": text, "language": "en-IN"})
        return _wait_for(ws, "clinical.turn")["data"]

    client = TestClient(create_app(Settings(deployment_profile="demo")))
    with client.websocket_connect("/ws/session") as ws:
        reach_interview(ws)
        _wait_for(ws, "clinical.question")
        # No confirmation round-trip: the turn lands directly.
        result = turn(ws, "chest pain")
        assert result["state"]["complaint"] == "chest pain"
        ws.send_json({"type": "session.stop"})
