"""Protocol recovery must preserve the patient and the current prompt."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from test_offline_workflow import Driver
from test_offline_workflow import settings as _settings  # noqa: F401

from medikiosk.app import create_app
from medikiosk.config import Settings
from medikiosk.session import ClinicalSession


def test_malformed_messages_do_not_disconnect(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        for value in ("{", "[]", "null"):
            ws.send_text(value)
            assert driver.until("error")["stage"] == "protocol"
        driver.act("choose", "en")
        assert driver.screen["stage"] == "who"


def test_double_language_tap_cannot_skip_role_or_consent(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        first = driver.act("choose", "hi")
        ws.send_json(first)
        assert driver.until("flow.ack")["duplicate"] is True
        assert driver.screen["stage"] == "who"
        ws.send_json(driver.envelope("choose", "hi"))
        assert driver.until("error")["stage"] == "flow"
        driver.act("choose", "self")
        assert driver.screen["stage"] == "consent"


def test_next_question_and_language_stay_in_sync(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical", language="hi")
        result = driver.turn("stomach pain")
        question = next(e for e in reversed(driver.events) if e["type"] == "clinical.question")
        assert result["language"] == "hi"
        assert question["id"] == result["next_question_id"] == "ask_duration"
        assert question["text"] == result["next_question"]


def test_overlapping_old_prompt_answers_are_rejected_not_rebound(settings, monkeypatch):
    original = ClinicalSession.process_transcript

    async def slow(self, *args, **kwargs):
        await asyncio.sleep(0.02)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(ClinicalSession, "process_transcript", slow)
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        for text in ("stomach pain", "three days", "four"):
            ws.send_json(driver.envelope("answer", text))
        assert driver.until("flow.ack")["type"] == "flow.ack"
        assert driver.until("error")["stage"] == "flow"
        assert driver.until("error")["stage"] == "flow"
        turns = [e["data"] for e in driver.events if e["type"] == "clinical.turn"]
        assert len(turns) == 1
        assert turns[0]["state"]["duration"] is None
        assert turns[0]["state"]["severity"] is None
        assert driver.turn("three days")["state"]["duration"] == "three days"


def test_confirmed_restart_rejects_old_patient_action(settings):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        old = driver.envelope("answer", "chest pain and short of breath")
        driver.act("restart")
        assert driver.screen["stage"] == "interview"
        driver.act("confirm")
        assert driver.screen["stage"] == "language"
        assert driver.session_id != old["session_id"]
        ws.send_json(old)
        assert driver.until("error")["stage"] == "flow"
        driver.reach_service("clinical")
        result = driver.turn("stomach pain")
        assert result["state"]["complaint"] == "abdominal pain"
        assert result["state"]["chest_pain"] is not True
        assert not result["should_alert_staff"]


def test_scan_routes_require_session_before_examining_image(settings):
    with TestClient(create_app(settings)) as client:
        for route in ("/api/abha-scan", "/api/ocr"):
            result = client.post(route, files={"image": ("bad.jpg", b"not an image")})
            assert result.status_code == 401


@pytest.mark.parametrize("profile", ["jetson", "pi", "demo"])
def test_offline_profiles_never_activate_cloud_keys(profile):
    settings = Settings(
        _env_file=None,
        deployment_profile=profile,
        openai_api_key="synthetic",
        sarvam_api_key="synthetic",
    )
    assert not settings.openai_configured
    assert not settings.sarvam_configured
