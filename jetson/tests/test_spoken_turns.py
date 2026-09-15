"""Spoken turns through the real PCM -> VAD -> ASR-boundary -> dispatcher path.

Synthetic audio and a fake recogniser: these test the wiring, not acoustics. They replaced the
readback tests when the "I heard X, is that correct?" step was removed - a spoken answer now
binds directly, and the review screen at the end is where a mishearing gets fixed.
"""

import struct
import threading
from collections import deque

import pytest
from fastapi.testclient import TestClient
from test_offline_workflow import Driver, clinical_review
from test_offline_workflow import settings as _settings  # noqa: F401

from medikiosk.app import create_app
from medikiosk.edge.runtime import pcm_to_wav
from medikiosk.edge.vad import FRAME_BYTES
from medikiosk.storage import EncryptedSessionStore


@pytest.fixture
def speech(monkeypatch):
    utterances = deque()
    condition = threading.Condition()
    prompts = []

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
        prompts.append(text)
        return pcm_to_wav(bytes(320))

    monkeypatch.setattr("medikiosk.app.WhisperCppSTT.health", lambda _: True)
    monkeypatch.setattr("medikiosk.app.WhisperCppSTT.transcribe", transcribe)
    # No Hindi service in tests: every language takes the whisper path.
    monkeypatch.setattr("medikiosk.app.IndicConformerSTT.health", lambda _: False)
    monkeypatch.setattr("medikiosk.app.SileroVAD", Vad)
    monkeypatch.setattr("medikiosk.app.VoiceBank.available", lambda *args: True)
    monkeypatch.setattr("medikiosk.app.VoiceBank.synthesize", synthesize)
    sound = struct.pack("<h", 1500) * (FRAME_BYTES // 2) * 10 + bytes(FRAME_BYTES * 24)

    def say(driver, text, expect="tts.end"):
        driver.ws.send_json(
            {
                "type": "playback.state",
                "session_id": driver.session_id,
                "revision": driver.revision,
                "playing": False,
            }
        )
        with condition:
            utterances.append(text)
        driver.ws.send_json(
            {"type": "audio.start", "session_id": driver.session_id, "revision": driver.revision}
        )
        driver.ws.send_bytes(sound)
        result = driver.until(expect)
        assert result["type"] == expect, result
        assert not utterances
        return result

    return say, prompts


def saved(settings, driver):
    store = EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
    return store.load_workflow(driver.token)["data"]


def test_the_opening_description_accumulates_until_the_patient_proceeds(settings, speech):
    """Item 5: speak into the box sentence by sentence; nothing is dispatched until Proceed."""

    say, prompts = speech
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        driver.until("tts.end")
        opening = next(e for e in driver.events if e["type"] == "clinical.question")
        assert opening["id"] == "ask_complaint"
        assert opening["accumulate"] is True
        assert "describe your problem" in opening["text"].lower()

        first = say(driver, "stomach pain", expect="transcript.final")
        second = say(driver, "since two days", expect="transcript.final")
        assert first["accumulate"] is True and second["accumulate"] is True
        assert not any(e["type"] == "clinical.turn" for e in driver.events)
        assert saved(settings, driver)["state"]["complaint"] is None

        # The tablet joined the pieces and the patient pressed Proceed.
        driver.act("answer", "stomach pain since two days")
        record = saved(settings, driver)
        assert record["state"]["complaint"] == "abdominal pain"
        assert record["state"]["duration"] == "two days"
        # Only what the description left empty is asked next.
        assert driver.question not in {"ask_complaint", "ask_duration"}
        assert all(
            not e.get("accumulate")
            for e in driver.events
            if e["type"] == "clinical.question" and e["id"] != "ask_complaint"
        )


def test_a_spoken_answer_binds_without_a_readback(settings, speech):
    """Item 2: no "I heard X, is that correct?" after every question."""

    say, prompts = speech
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        driver.act("answer", "stomach pain")
        driver.until("tts.end")
        assert driver.question == "ask_duration"
        say(driver, "five days")
        record = saved(settings, driver)
        assert record["state"]["duration"] == "five days"
        assert not any("Is that correct" in p or "सही है" in p for p in prompts)
        answer = next(a for a in record["flow"]["answers"] if a["id"] == "ask_duration")
        assert answer["method"] == "voice"
        assert answer["answer"] == "five days"


def test_spoken_commands_still_work_during_the_description(settings, speech):
    """A patient saying "help" mid-description gets help, not a transcript line."""

    say, _ = speech
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        driver.until("tts.end")
        result = say(driver, "help", expect="staff.alert")
        assert result["status"] == "requested"
        assert driver.question == "ask_complaint"


@pytest.mark.parametrize("command", ["restart", "withdraw permission"])
def test_consequential_spoken_commands_can_be_cancelled(settings, speech, command):
    say, _ = speech
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        driver.act("answer", "stomach pain")
        driver.until("tts.end")
        say(driver, command)
        assert driver.screen.get("options") and driver.screen["stage"] == "interview"
        say(driver, "no")
        assert saved(settings, driver)["state"]["complaint"] == "abdominal pain"
        assert driver.question == "ask_duration"


def test_spoken_restart_retires_the_old_capability(settings, speech):
    say, _ = speech
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        driver.reach_service("clinical")
        driver.until("tts.end")
        old_token = driver.token
        say(driver, "restart")
        say(driver, "yes", expect="session.id")
        driver.until("flow.screen")
        assert driver.token != old_token
        assert driver.screen["stage"] == "language"
    store = EncryptedSessionStore(settings.session_store_path, settings.session_encryption_key)
    assert store.load_workflow(old_token) is None


def test_review_edit_by_voice_rebinds_directly(settings, speech):
    say, _ = speech
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("edit", "ask_duration")
        driver.until("tts.end")
        assert driver.question == "ask_duration"
        say(driver, "six days")
        assert driver.screen["stage"] == "review"
        assert saved(settings, driver)["state"]["duration"] == "six days"
