import asyncio

import pytest
from fastapi.testclient import TestClient

from medikiosk.app import create_app
from medikiosk.config import Settings
from medikiosk.providers.local_llm_provider import LocalLLMClinicalExtractor
from medikiosk.providers.whisper_provider import WhisperCppSTT
from medikiosk.session import ClinicalSession


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(WhisperCppSTT, 'health', lambda self: False)
    monkeypatch.setattr(LocalLLMClinicalExtractor, 'health', lambda self: False)
    with TestClient(create_app(Settings(deployment_profile='demo'))) as test_client:
        yield test_client


def wait(ws, kind):
    for _ in range(40):
        msg = ws.receive_json()
        if msg['type'] == kind:
            return msg
    raise AssertionError(f'No {kind} event')


def interview(ws, language='en'):
    wait(ws, 'flow.screen')
    for command in ({'type': 'flow.language', 'value': language},
                    {'type': 'flow.abha', 'value': ''},
                    {'type': 'flow.who', 'value': 'self'}):
        ws.send_json(command)
        wait(ws, 'flow.screen')
    assert wait(ws, 'clinical.question')['id'] == 'ask_complaint'


def test_malformed_messages_do_not_disconnect(client):
    with client.websocket_connect('/ws/session') as ws:
        wait(ws, 'flow.screen')
        for value in ('{', '[]', 'null'):
            ws.send_text(value)
            assert wait(ws, 'error')['stage'] == 'protocol'
        ws.send_json({'type': 'flow.language', 'value': 'en'})
        assert wait(ws, 'flow.screen')['data']['stage'] == 'abha'
        ws.send_json({'type': 'session.stop'})


def test_double_language_tap_does_not_skip_abha(client):
    with client.websocket_connect('/ws/session') as ws:
        wait(ws, 'flow.screen')
        ws.send_json({'type': 'flow.language', 'value': 'hi'})
        assert wait(ws, 'flow.screen')['data']['stage'] == 'abha'
        ws.send_json({'type': 'flow.language', 'value': 'hi'})
        assert wait(ws, 'error')['stage'] == 'flow'
        ws.send_json({'type': 'flow.abha', 'value': '123'})
        assert wait(ws, 'error')['stage'] == 'abha'
        ws.send_json({'type': 'flow.abha', 'value': ''})
        assert wait(ws, 'flow.screen')['data']['stage'] == 'who'
        ws.send_json({'type': 'session.stop'})


def test_next_question_event_and_language_stay_in_sync(client):
    with client.websocket_connect('/ws/session') as ws:
        interview(ws, 'hi')
        ws.send_json({'type': 'transcript.submit', 'text': 'stomach pain', 'language': 'en-IN'})
        result = wait(ws, 'clinical.turn')['data']
        question = wait(ws, 'clinical.question')
        assert result['language'] == 'hi'
        assert question['id'] == result['next_question_id'] == 'ask_duration'
        assert question['text'] == result['next_question']
        ws.send_json({'type': 'session.stop'})


def test_overlapping_answers_bind_in_order(client, monkeypatch):
    original = ClinicalSession.process_transcript

    async def slow(self, *args, **kwargs):
        await asyncio.sleep(0.02)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(ClinicalSession, 'process_transcript', slow)
    with client.websocket_connect('/ws/session') as ws:
        interview(ws)
        for text in ('stomach pain', 'three days', 'four'):
            ws.send_json({'type': 'transcript.submit', 'text': text})
        results = [wait(ws, 'clinical.turn')['data'] for _ in range(3)]
        assert results[-1]['state']['duration'] == 'three days'
        assert results[-1]['state']['severity'] == 4
        ws.send_json({'type': 'session.stop'})


def test_restart_cancels_old_patient_turn(client, monkeypatch):
    original = ClinicalSession.process_transcript

    async def slow(self, *args, **kwargs):
        await asyncio.sleep(0.1)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(ClinicalSession, 'process_transcript', slow)
    with client.websocket_connect('/ws/session') as ws:
        interview(ws)
        ws.send_json({'type': 'transcript.submit', 'text': 'chest pain and short of breath'})
        wait(ws, 'clinical.processing')
        ws.send_json({'type': 'flow.restart'})
        assert wait(ws, 'flow.screen')['data']['stage'] == 'language'
        ws.send_json({'type': 'flow.language', 'value': 'en'})
        wait(ws, 'flow.screen')
        ws.send_json({'type': 'flow.abha', 'value': ''})
        wait(ws, 'flow.screen')
        ws.send_json({'type': 'flow.who', 'value': 'self'})
        wait(ws, 'flow.screen')
        assert wait(ws, 'clinical.question')['id'] == 'ask_complaint'
        ws.send_json({'type': 'transcript.submit', 'text': 'stomach pain'})
        result = wait(ws, 'clinical.turn')['data']
        assert result['state']['complaint'] == 'abdominal pain'
        assert result['state']['chest_pain'] is not True
        assert not result['should_alert_staff']
        ws.send_json({'type': 'session.stop'})


def test_bad_image_is_recoverable(client):
    result = client.post('/api/abha-scan', files={'image': ('bad.jpg', b'not an image')})
    assert result.status_code == 422
    result = client.post('/api/ocr', files={'image': ('bad.jpg', b'not an image')})
    assert result.status_code == 422


@pytest.mark.parametrize('profile', ['jetson', 'pi', 'demo'])
def test_offline_profiles_never_activate_cloud_keys(profile):
    settings = Settings(deployment_profile=profile, openai_api_key='test', sarvam_api_key='test')
    assert not settings.openai_configured
    assert not settings.sarvam_configured
