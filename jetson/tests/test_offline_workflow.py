"""Synthetic protocol-2 journeys; no devices, patient records, or network calls."""

import json
import sqlite3
import time
from uuid import uuid4

import anyio
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from medikiosk.app import create_app
from medikiosk.config import Settings
from medikiosk.kiosk import prakriti
from medikiosk.kiosk.consent import ConsentLedger
from medikiosk.kiosk.flow import KioskFlow, Stage
from medikiosk.kiosk.protocol import SessionGuard
from medikiosk.kiosk.queue import QueueStore
from medikiosk.kiosk.voice_actions import (
    Decision,
    match_option,
    parse_age,
    parse_command,
    parse_decision,
)
from medikiosk.models import PatientState
from medikiosk.storage import EncryptedSessionStore


def receive(ws):
    async def bounded():
        with anyio.fail_after(3):
            return await ws._send_rx.receive()

    message = ws.portal.call(bounded)
    ws._raise_on_close(message)
    return json.loads(message["text"])


class Driver:
    def __init__(self, ws):
        self.ws = ws
        self.screen = None
        self.report = None
        self.question = None
        self.events = []
        self.until("configuration.required")

    def until(self, kind):
        for _ in range(100):
            event = receive(self.ws)
            self.events.append(event)
            self.session_id = event["session_id"]
            self.revision = event["revision"]
            if event["type"] == "session.id":
                self.token = event["session_token"]
            elif event["type"] == "flow.screen":
                self.screen = event["data"]
                self.question = self.screen.get("question_id")
            elif event["type"] == "clinical.question":
                self.question = event["id"]
            elif event["type"] == "flow.report":
                self.report = event["data"]
            if event["type"] in {kind, "error"}:
                return event
        pytest.fail(f"No {kind} within 100 events")

    def envelope(self, action, value=None):
        return dict(
            type="flow.action",
            session_id=self.session_id,
            revision=self.revision,
            action_id=str(uuid4()),
            action=action,
            value=value,
            question_id=self.question,
        )

    def act(self, action, value=None):
        envelope = self.envelope(action, value)
        self.ws.send_json(envelope)
        result = self.until("flow.ack")
        assert result["type"] == "flow.ack", result
        return envelope

    def reach_service(self, service="prakriti", language="en", abha=None):
        self.act("choose", language)
        self.act("choose", "self")
        self.act("choose", "yes")
        assert self.screen["stage"] == "registration"
        for _ in range(3):
            self.act("unknown")
        self.act("answer", abha) if abha else self.act("skip")
        self.act("choose", service)

    def turn(self, text):
        before = len(self.events)
        self.act("answer", text)
        return next(e["data"] for e in self.events[before:] if e["type"] == "clinical.turn")

    @property
    def scan_headers(self):
        return {
            "X-Kiosk-Session": self.session_id,
            "X-Kiosk-Token": self.token,
            "X-Kiosk-Revision": str(self.revision),
        }


@pytest.fixture(name="settings")
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr("medikiosk.app.WhisperCppSTT.health", lambda _: False)
    monkeypatch.setattr("medikiosk.app.IndicConformerSTT.health", lambda _: False)
    return Settings(
        _env_file=None,
        deployment_profile="demo",
        clinical_llm_enabled=False,
        openai_api_key=None,
        sarvam_api_key=None,
        session_store_path=tmp_path / "sessions.db",
        session_encryption_key=Fernet.generate_key().decode(),
    )


def consented_flow():
    flow = KioskFlow()
    flow.action("choose", "en")
    flow.action("choose", "self")
    flow.action("choose", "yes")
    assert flow.consent.allows("local_intake")
    return flow


@pytest.mark.parametrize(
    "phrase", ["not sure", "no yes", "हाँ नहीं", "yes but do not upload", "है", "नहीं है"]
)
def test_ambiguous_confirmation_is_not_yes(phrase):
    assert parse_decision(phrase) is Decision.UNCERTAIN


@pytest.mark.parametrize(
    "phrase", ["do not restart", "back pain", "please do not skip", "helped yesterday"]
)
def test_command_substrings_do_not_navigate(phrase):
    assert parse_command(phrase) is None


def test_all_numbered_options_including_ten_are_selectable():
    options = [{"value": str(i), "label": f"Choice {i}"} for i in range(1, 13)]
    for number in range(1, 13):
        assert match_option(f"option {number}", options) == str(number)
    assert match_option("विकल्प १०", options) == "10"
    assert match_option("option ten", options) == "10"
    assert match_option("option 100", options) is None
    assert (
        match_option("non veg", [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}])
        is None
    )


def test_permissions_are_separate_and_withdrawal_preserves_audit():
    consent = ConsentLedger()
    assert not consent.allows("local_intake")
    consent.record("local_intake", "granted", "en", "self", "voice")
    assert consent.allows("local_intake")
    assert not consent.allows("local_documents")
    assert not consent.allows("cloud_intake")
    consent.withdraw("local_intake")
    assert not consent.allows("local_intake")
    assert [d.decision for d in consent.decisions] == ["granted", "withdrawn"]
    assert consent.decisions[0].notice_hash == consent.decisions[1].notice_hash


def test_no_next_bypass_and_refusal_does_not_collect():
    flow = KioskFlow()
    for action in ("next", "answer", "document", "confirm"):
        with pytest.raises(ValueError):
            flow.action(action, "synthetic")
    flow.action("choose", "en")
    flow.action("choose", "self")
    flow.action("choose", "no")
    assert flow.stage is Stage.DECLINED
    assert flow.answers == []
    with pytest.raises(ValueError):
        flow.action("answer", "synthetic")


def test_registration_zero_binds_without_a_readback():
    flow = consented_flow()
    flow.action("unknown")
    flow.action("answer", 0)
    assert flow.registration["age"] == 0
    assert flow.registration_index == 2, "straight on to the next field"
    with pytest.raises(ValueError):
        flow.action("answer", "")  # an empty answer is not an answer; skip must be explicit


def test_full_prakriti_with_unknown_never_claims_complete():
    flow = consented_flow()
    for _ in range(3):
        flow.action("unknown")
    flow.action("skip")
    flow.action("choose", "prakriti")
    flow.action("choose", "no")
    seen = []
    for index, item in enumerate(prakriti.ITEMS):
        screen = flow.screen(PatientState())
        assert screen["question_id"] == item.id
        assert screen["progress"] == [index + 1, 68]
        seen.append(item.id)
        flow.action(
            "unknown" if index == 0 else "choose",
            screen["options"][0]["value"],
            question_id=item.id,
        )
    assert len(set(seen)) == 68
    assert flow.prakriti_record["complete"] is False
    assert flow.prakriti_record["prakriti"] is None
    assert flow.stage is Stage.CONSENT
    assert flow.consent_purpose == "local_documents"
    flow.action("choose", "no")
    assert flow.stage is Stage.REVIEW
    restored = KioskFlow.from_snapshot(flow.snapshot())
    assert restored.snapshot() == flow.snapshot()


@pytest.mark.parametrize("outcome", ["unknown", "refuse"])
def test_previous_completion_edit_keeps_unknown_distinct_and_cancellable(outcome):
    flow = consented_flow()
    for _ in range(3):
        flow.action("unknown")
    flow.action("skip")
    flow.action("choose", "prakriti")
    flow.action("choose", "yes")
    flow.action("choose", "no")
    flow.action("edit", "prakriti.previous")
    flow.action("cancel")
    assert flow.stage is Stage.REVIEW
    assert flow.prakriti_previously_filled is True
    flow.action("edit", "prakriti.previous")
    flow.action(outcome)
    assert flow.edit_target is None
    assert flow.prakriti_previously_filled is None
    assert flow.screen(PatientState())["question_id"] == prakriti.ITEMS[0].id
    report = flow.finish(PatientState(), [])
    assert report["previous_prakriti"]["self_reported"] is None
    assert report["previous_prakriti"]["status"] == (
        "refused" if outcome == "refuse" else "unresolved"
    )


def test_completed_questionnaire_edits_recompute_without_overflow():
    flow = consented_flow()
    for _ in range(3):
        flow.action("unknown")
    flow.action("skip")
    flow.action("choose", "prakriti")
    flow.action("choose", "no")
    for item in prakriti.ITEMS:
        flow.action("choose", flow.screen(PatientState())["options"][0]["value"], item.id)
    flow.action("choose", "no")
    assert flow.prakriti_record["complete"] is True
    target = prakriti.ITEMS[0].id
    flow.action("edit", target)
    assert flow.screen(PatientState())["progress"] == [1, 68]
    assert "cancel" in flow.screen(PatientState())["allowed_actions"]
    flow.action("unknown", question_id=target)
    assert flow.stage is Stage.REVIEW
    assert flow.prakriti_record["complete"] is False
    assert flow.prakriti_record["prakriti"] is None
    assert target not in flow.prakriti_answers
    assert flow.ledger.current(target) is None
    flow.action("edit", "prakriti.previous")
    flow.action("unknown")
    assert flow.stage is Stage.REVIEW
    assert flow.edit_target is None


def test_workflow_and_queue_payloads_are_encrypted(settings):
    store = EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
    guard = SessionGuard()
    payload = {
        "guard": guard.snapshot(),
        "status": "active",
        "flow": consented_flow().snapshot(),
        "state": {"synthetic": "PRIVATE_SENTINEL"},
    }
    store.save_workflow(guard.session_id, payload, guard.token)
    reopened = EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
    assert reopened.load_workflow(guard.token)["data"] == payload
    assert reopened.load_workflow(SessionGuard().token) is None
    assert b"PRIVATE_SENTINEL" not in settings.session_store_path.read_bytes()
    assert guard.token.encode() not in settings.session_store_path.read_bytes()
    path = settings.session_store_path.with_name("queue-test.db")
    queue = QueueStore(path, settings.session_encryption_key)
    report = {
        "clinical": {"complaint": "PRIVATE_SENTINEL"},
        "routing": {"reason": "PRIVATE_REASON"},
    }
    first = queue.assign(guard.session_id, report)
    again = QueueStore(path, settings.session_encryption_key).assign(guard.session_id, report)
    assert first == again
    assert again.complaint == "PRIVATE_SENTINEL"
    assert b"PRIVATE_SENTINEL" not in path.read_bytes()
    assert b"PRIVATE_REASON" not in path.read_bytes()


def test_protocol_rejects_bypass_and_duplicate_does_not_grant_consent_twice(settings):
    with (
        TestClient(create_app(settings)) as client,
        client.websocket_connect("/ws/session", subprotocols=["medikiosk.v2"]) as ws,
    ):
        driver = Driver(ws)
        ws.send_json(driver.envelope("next"))
        assert driver.until("flow.ack")["type"] == "error"
        driver.act("choose", "en")
        driver.act("choose", "self")
        first_yes = driver.act("choose", "yes")
        ws.send_json(first_yes)
        assert driver.until("flow.ack")["duplicate"] is True
        assert driver.screen["stage"] == "registration"
        assert client.post("/api/ocr").status_code != 200


@pytest.mark.parametrize("question_id", [None, "", "another-question"])
@pytest.mark.parametrize(
    "stage,action,value",
    [
        ("consent", "choose", "yes"),
        ("registration", "answer", "Synthetic Person"),
        ("registration", "unknown", None),
        ("clinical", "answer", "stomach pain"),
        ("clinical", "refuse", None),
        ("prakriti", "unknown", None),
    ],
)
def test_answer_requires_current_question_identity(settings, stage, action, value, question_id):
    store = EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        if stage in {"consent", "registration"}:
            driver.act("choose", "en")
            driver.act("choose", "self")
            if stage == "registration":
                driver.act("choose", "yes")
        else:
            driver.reach_service(stage)
            if stage == "prakriti":
                driver.act("choose", "no")
        expected = driver.question
        assert expected
        envelope = driver.envelope(action, value)
        envelope["question_id"] = question_id
        before = store.load_workflow(driver.token)
        start = len(driver.events)
        ws.send_json(envelope)
        result = driver.until("flow.ack")
        assert result["type"] == "error" and result["stage"] == "flow"
        assert store.load_workflow(driver.token) == before
        assert not any(
            e["type"] in {"flow.ack", "flow.screen", "clinical.turn"} for e in driver.events[start:]
        )
        envelope["question_id"] = expected
        ws.send_json(envelope)
        assert driver.until("flow.ack")["duplicate"] is False


def test_failed_durable_write_never_acknowledges_or_advances(settings, monkeypatch):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.act("choose", "en")
        driver.act("choose", "self")
        driver.act("choose", "yes")
        envelope = driver.envelope("unknown")
        original = EncryptedSessionStore.save_workflow

        def fail(*args, **kwargs):
            raise OSError("Synthetic disk full")

        monkeypatch.setattr(EncryptedSessionStore, "save_workflow", fail)
        before = len(driver.events)
        ws.send_json(envelope)
        assert driver.until("flow.ack")["type"] == "error"
        assert all(e["type"] not in {"flow.ack", "flow.screen"} for e in driver.events[before:])
        monkeypatch.setattr(EncryptedSessionStore, "save_workflow", original)
        ws.send_json(envelope)
        assert driver.until("flow.ack")["duplicate"] is False
        assert driver.screen["stage"] == "registration"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("forty two", 42),
        ("मेरी उम्र चालीस साल है", 40),
        ("0", 0),
        ("४२", 42),
        ("forty or fifty", None),
        ("30 to 40", None),
        ("I do not know", None),
    ],
)
def test_spoken_registration_age_is_conservative(text, expected):
    assert parse_age(text, "hi") == expected


def test_full_prakriti_voice_path_uses_pcm_and_real_dispatch(settings, monkeypatch):
    import struct
    import threading
    from collections import deque

    from medikiosk.edge.vad import FRAME_BYTES

    utterances = deque()
    condition = threading.Condition()
    spoken_prompts = []

    class Vad:
        def __init__(self, *args):
            pass

        def reset(self):
            pass

        def probability(self, frame):
            return 1.0 if any(frame) else 0.0

    def transcribe(self, wav, language):
        assert wav.startswith(b"RIFF")
        with condition:
            assert utterances, "Unexpected ASR call"
            return utterances.popleft(), language or "en"

    def synthesize(self, text, language):
        spoken_prompts.append(text)
        from medikiosk.edge.runtime import pcm_to_wav

        return pcm_to_wav(bytes(320))

    monkeypatch.setattr("medikiosk.app.WhisperCppSTT.health", lambda _: True)
    monkeypatch.setattr("medikiosk.app.WhisperCppSTT.transcribe", transcribe)
    monkeypatch.setattr("medikiosk.app.SileroVAD", Vad)
    monkeypatch.setattr("medikiosk.app.VoiceBank.available", lambda *args: True)
    monkeypatch.setattr("medikiosk.app.VoiceBank.synthesize", synthesize)
    sound = struct.pack("<h", 1500) * (FRAME_BYTES // 2) * 10 + bytes(FRAME_BYTES * 24)

    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)

        def say(text, readback=False):
            driver.until("tts.end")
            # Simulate native completion, not just synthesis completion.
            ws.send_json(
                {
                    "type": "playback.state",
                    "session_id": driver.session_id,
                    "revision": driver.revision,
                    "playing": False,
                }
            )
            with condition:
                utterances.append(text)
            ws.send_json(
                {
                    "type": "audio.start",
                    "session_id": driver.session_id,
                    "revision": driver.revision,
                }
            )
            ws.send_bytes(sound)
            event = driver.until("flow.screen" if not readback else "tts.start")
            assert event["type"] != "error", event

        say("English")
        say("Myself")
        say("yes")  # one explicit yes to the read-aloud notice; no second "confirm" step
        say("Synthetic Person")
        say("forty two")
        say("prefer not to answer")
        say("skip")
        say("Full Prakriti questionnaire")
        say("no")
        for index in range(68):
            assert driver.screen["stage"] == "prakriti"
            assert driver.screen["progress"] == [index + 1, 68]
            say("unknown" if index == 0 else "option one")
        say("no")  # Refuse optional document permission.
        assert driver.screen["stage"] == "review"
        say("edit answer 2")
        assert driver.screen["stage"] == "registration"
        say("forty three")
        assert driver.screen["stage"] == "review"
        say("confirm")
        assert driver.report["completion"] == "saved_local"
        assert driver.report["registration"]["age"] == 43
        assert driver.report["prakriti"]["complete"] is False
        assert driver.report["prakriti"]["prakriti"] is None
        assert len(driver.report["questionnaire_outcomes"]["prakriti"]) == 68
        assert all(a["method"] == "voice" for a in driver.report["accepted_answers"])
        assert any("Synthetic Person" in text and "43" in text for text in spoken_prompts)
        assert not utterances


def clinical_review(driver):
    driver.reach_service("clinical")
    driver.turn("stomach pain")
    driver.turn("three days")
    for _ in range(30):
        if driver.screen["stage"] != "interview":
            break
        driver.act("unknown")
    assert driver.screen["stage"] == "ayurveda"
    for _ in range(30):
        if driver.screen["stage"] != "ayurveda":
            break
        driver.act("unknown")
    assert driver.screen["stage"] == "prakriti"
    driver.act("choose", "yes")
    driver.act("choose", "no")
    assert driver.screen["stage"] == "review"


@pytest.mark.parametrize("resolution", ["cancel", "unknown", "refuse", "answer"])
def test_clinical_review_edit_returns_to_review_with_correct_evidence(settings, resolution):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("edit", "ask_duration")
        assert driver.question == "ask_duration"
        driver.act(resolution, "five days" if resolution == "answer" else None)
        assert driver.screen["stage"] == "review"
        driver.act("confirm")
        report = driver.report
        expected = (
            "three days"
            if resolution == "cancel"
            else "five days"
            if resolution == "answer"
            else None
        )
        assert report["clinical"]["duration"] == expected
        answer = next(a for a in report["accepted_answers"] if a["id"] == "ask_duration")
        assert answer["status"] == (
            "refused"
            if resolution == "refuse"
            else "unresolved"
            if resolution == "unknown"
            else "answered"
        )
        live = [
            e
            for e in report["provenance"]["entries"]
            if e["key"] == "duration" and e.get("superseded_by") is None
        ]
        assert ([e["value"] for e in live] == [expected]) if expected else not live


@pytest.mark.parametrize("resolution", ["cancel", "unknown", "refuse", "answer"])
def test_registration_age_correction_clears_clinical_value_and_provenance(settings, resolution):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("edit", "registration.age")
        driver.act("answer", 42)
        driver.act("edit", "registration.age")
        driver.act(resolution, 0 if resolution == "answer" else None)
        driver.act("repeat")
        assert driver.screen["stage"] == "review"
        driver.act("confirm")
        expected = 42 if resolution == "cancel" else 0 if resolution == "answer" else None
        assert driver.report["registration"]["age"] == expected
        assert driver.report["patient"]["age_years"] == expected
        live = [
            e
            for e in driver.report["provenance"]["entries"]
            if e["key"] == "age_years" and e.get("superseded_by") is None
        ]
        assert [e["value"] for e in live] == ([expected] if expected is not None else [])


def test_idle_kiosk_warns_extends_then_closes_for_next_patient(settings):
    from starlette.websockets import WebSocketDisconnect

    settings.idle_timeout_s = 1.0
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        # Nobody's data is on the language screen, so it never times out.
        time.sleep(1.6)
        driver.act("choose", "en")
        driver.act("choose", "self")
        assert driver.screen["stage"] == "consent"
        warning = driver.until("session.idle")
        assert 0 < warning["remaining"] <= 1.0
        driver.act("more_time")
        time.sleep(1.2)
        # Doubled allowance: still open and re-warned rather than closed.
        assert driver.until("session.idle")["type"] == "session.idle"
        token, session_id = driver.token, driver.session_id
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(200):
                driver.until("session.idle")
        assert closed.value.code == 4408
    # The encounter itself is kept, so the same patient can still resume with their capability.
    settings.idle_timeout_s = 600.0
    with (
        TestClient(create_app(settings)) as client,
        client.websocket_connect(
            "/ws/session", subprotocols=["medikiosk.v2", f"resume.{token}"]
        ) as ws,
    ):
        resumed = Driver(ws)
        assert resumed.session_id == session_id
        assert resumed.screen["stage"] == "consent"


def test_interview_restart_and_withdraw_use_confirmation_options(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        driver.act("withdraw")
        assert "Stop new collection" in driver.screen["headline"]
        before = len(driver.events)
        driver.act("choose", "no")
        assert not any(e["type"] == "clinical.turn" for e in driver.events[before:])
        assert driver.question == "ask_complaint"
        driver.act("restart")
        driver.act("choose", "yes")
        assert driver.screen["stage"] == "language"


@pytest.mark.parametrize("boundary", ["retire_old", "insert_new"])
@pytest.mark.parametrize("retry", [False, True])
def test_failed_restart_keeps_original_capability_durable(settings, boundary, retry):
    store = EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical", language="hi")
        driver.turn("stomach pain")
        driver.act("restart")
        old_id, old_token, old_revision = driver.session_id, driver.token, driver.revision
        before = store.load_workflow(old_token)
        restart_action = driver.envelope("choose", "yes")
        # Fail inside SQLite, after any earlier statement in the handoff has executed.
        # Inspect the durable row before disconnect cleanup can rewrite it.
        with sqlite3.connect(settings.session_store_path) as connection:
            event = "UPDATE" if boundary == "retire_old" else "INSERT"
            operator = "=" if boundary == "retire_old" else "!="
            connection.execute(
                f"CREATE TRIGGER fail_restart BEFORE {event} ON workflows "
                f"WHEN NEW.session_id {operator} '{old_id}' "
                "BEGIN SELECT RAISE(ABORT, 'Synthetic restart storage failure'); END"
            )
        try:
            start = len(driver.events)
            ws.send_json(restart_action)
            assert driver.until("error")["stage"] == "flow"
            assert store.load_workflow(old_token) == before
            assert (driver.session_id, driver.token, driver.revision) == (
                old_id,
                old_token,
                old_revision,
            )
            assert not any(
                e["type"] in {"session.id", "flow.screen", "flow.ack"}
                for e in driver.events[start:]
            )
            with sqlite3.connect(settings.session_store_path) as connection:
                assert connection.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] == 1
        finally:
            with sqlite3.connect(settings.session_store_path) as connection:
                connection.execute("DROP TRIGGER IF EXISTS fail_restart")
        if retry:
            ws.send_json(restart_action)
            assert driver.until("flow.ack")["duplicate"] is False
            assert driver.screen["stage"] == "language"
            assert driver.token != old_token
            assert store.load_workflow(old_token) is None
        else:
            driver.act("choose", "no")
            driver.act("answer", "three days")
            saved = store.load_workflow(old_token)["data"]
            assert saved["state"]["complaint"] == "abdominal pain"
            assert saved["state"]["duration"] == "three days"
        resume_token, resume_id = driver.token, driver.session_id
    with (
        TestClient(create_app(settings)) as client,
        client.websocket_connect(
            "/ws/session", subprotocols=["medikiosk.v2", f"resume.{resume_token}"]
        ) as ws,
    ):
        recovered = Driver(ws)
        assert recovered.session_id == resume_id
        assert recovered.screen["stage"] == ("language" if retry else "interview")
        if not retry:
            assert recovered.screen["language"] == "hi"


def test_restart_commit_precedes_delivery_and_retires_old_patient(settings, monkeypatch):
    from starlette.websockets import WebSocket, WebSocketDisconnect

    store = EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
    original = WebSocket.send_json
    undelivered = []
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        driver.turn("stomach pain")
        driver.act("restart")
        old_id, old_token = driver.session_id, driver.token

        async def drop_replacement(self, data, *args, **kwargs):
            if data["type"] == "session.id" and data["session_id"] != old_id:
                fresh = store.load_workflow(data["session_token"])
                assert fresh["session_id"] == data["session_id"]
                assert store.load_workflow(old_token) is None
                undelivered.append(data)
                await self.close(code=1011)
                raise WebSocketDisconnect(code=1011)
            await original(self, data, *args, **kwargs)

        monkeypatch.setattr(WebSocket, "send_json", drop_replacement)
        ws.send_json(driver.envelope("choose", "yes"))
        with pytest.raises(WebSocketDisconnect):
            driver.until("flow.ack")
        assert len(undelivered) == 1
    monkeypatch.setattr(WebSocket, "send_json", original)
    with TestClient(create_app(settings)) as client:
        with (
            pytest.raises(WebSocketDisconnect) as denied,
            client.websocket_connect(
                "/ws/session", subprotocols=["medikiosk.v2", f"resume.{old_token}"]
            ) as ws,
        ):
            Driver(ws)
        assert denied.value.code == 4404
        # Only the captured, undelivered NEW capability can open the fresh encounter.
        new_token = undelivered[0]["session_token"]
        with client.websocket_connect(
            "/ws/session", subprotocols=["medikiosk.v2", f"resume.{new_token}"]
        ) as ws:
            recovered = Driver(ws)
            assert recovered.screen["stage"] == "language"
            record = store.load_workflow(new_token)["data"]
            assert record["state"]["complaint"] is None
            assert record["flow"]["answers"] == []
            assert record["flow"]["consent"]["decisions"] == []


@pytest.mark.parametrize("boundary", ["save_report", "queue_assign", "save_completion"])
def test_finalization_failure_never_publishes_queue_and_retry_is_idempotent(
    settings, monkeypatch, boundary
):
    owner, name = (
        (QueueStore, "assign") if boundary == "queue_assign" else (EncryptedSessionStore, boundary)
    )
    original = getattr(owner, name)

    def fail(*args, **kwargs):
        raise OSError("Synthetic disk failure")

    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service()
        driver.act("choose", "yes")
        driver.act("choose", "no")
        envelope = driver.envelope("confirm")
        monkeypatch.setattr(owner, name, fail)
        before = len(driver.events)
        ws.send_json(envelope)
        assert driver.until("error")["stage"] == "flow"
        assert not any(e["type"] in {"flow.report", "flow.ack"} for e in driver.events[before:])
        queue = QueueStore(
            settings.session_store_path.with_name("queue.db"), settings.session_encryption_key
        )
        assert queue.waiting() == []
        monkeypatch.setattr(owner, name, original)
        ws.send_json(envelope)
        assert driver.until("flow.ack")["type"] == "flow.ack"
        assert driver.report["completion"] == "saved_local"
        assert len(queue.waiting()) == 1
        ws.send_json(envelope)
        assert driver.until("flow.ack")["duplicate"] is True
        assert len(queue.waiting()) == 1


def test_committed_report_recovers_queue_publication_after_restart(settings, monkeypatch):
    original = QueueStore.publish

    def fail(*args):
        raise OSError("Synthetic queue disk failure")

    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service()
        driver.act("choose", "yes")
        driver.act("choose", "no")
        monkeypatch.setattr(QueueStore, "publish", fail)
        driver.act("confirm")
        assert driver.report["completion"] == "saved_local"
        session_id = driver.session_id
    queue = QueueStore(
        settings.session_store_path.with_name("queue.db"), settings.session_encryption_key
    )
    assert queue.waiting() == []
    assert queue.get(session_id).state == "FINALIZING"
    monkeypatch.setattr(QueueStore, "publish", original)
    with TestClient(create_app(settings)):
        assert len(queue.waiting()) == 1
    queue.set_state(session_id, "COMPLETED")
    with TestClient(create_app(settings)):
        assert queue.get(session_id).state == "COMPLETED"


def test_saved_receipt_survives_backend_restart_without_duplicate_queue(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service()
        driver.act("choose", "yes")  # Self-reported previous completion; no invented result.
        driver.act("choose", "no")  # Refuse document reading.
        assert driver.screen["stage"] == "review"
        driver.act("confirm")
        assert driver.report["completion"] == "saved_local"
        assert driver.report["cloud_status"] == "not_requested"
        assert driver.report["accepted_answers"]
        assert driver.report["registration"] == {"name": None, "age": None, "gender": None}
        session_id, token, number = (
            driver.session_id,
            driver.token,
            driver.report["queue_entry"]["number"],
        )
    with (
        TestClient(create_app(settings)) as client,
        client.websocket_connect(
            "/ws/session", subprotocols=["medikiosk.v2", f"resume.{token}"]
        ) as ws,
    ):
        resumed = Driver(ws)
        assert resumed.session_id == session_id
        assert resumed.report["completion"] == "saved_local"
        assert resumed.report["queue_entry"]["number"] == number
        ws.send_json(resumed.envelope("answer", "not another patient"))
        assert resumed.until("flow.ack")["type"] == "error"
    queue = QueueStore(
        settings.session_store_path.with_name("queue.db"), settings.session_encryption_key
    )
    assert len(queue.waiting()) == 1
