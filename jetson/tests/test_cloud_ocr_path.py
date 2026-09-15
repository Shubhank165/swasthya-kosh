"""The handwritten-document path, end to end through the server, with the network faked.

What has to hold, in order of how badly it hurts if it does not:

  1. With the feature off - the default - nothing is held and nothing is sent. The kiosk is the
     offline kiosk it was.
  2. A client cannot make the kiosk upload an arbitrary file by naming a handle it did not get.
  3. At finish(), the record is ingested first and the held pages are uploaded against its
     intake_id - and an ambiguous upload is never repeated.
"""

from __future__ import annotations

import contextlib
import io
import json
import urllib.error
import urllib.parse

from fastapi.testclient import TestClient

from medikiosk.app import create_app
from medikiosk.config import Settings
from medikiosk.kiosk import ayurveda
from medikiosk.kiosk.document_outbox import AMBIGUOUS, UPLOADED, DocumentOutbox
from medikiosk.providers import intake_api as intake_api_module


def _wait_for(ws, message_type: str) -> dict:
    while True:
        message = ws.receive_json()
        if message["type"] == message_type:
            return message


def _screen(ws) -> dict:
    return _wait_for(ws, "flow.screen")["data"]


class ScriptedNetwork:
    """Stands in for urllib.request.urlopen. Records every request; answers from a script."""

    def __init__(self) -> None:
        self.requests: list = []
        self.script: list = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        # The script models the intake API. The kiosk's own loopback health checks (whisper,
        # ollama) go through the same urlopen and must neither consume it nor be scripted.
        if urllib.parse.urlsplit(request.full_url).hostname in ("127.0.0.1", "localhost", "::1"):
            step = ({"ok": True}, 200)
        else:
            step = self.script.pop(0) if self.script else ({"ok": True}, 200)
        if isinstance(step, BaseException):
            raise step
        body, status = step
        if body == "echo-intake-id":
            # Mirrors the real API: it returns the intake_id the kiosk chose.
            body = {"intake_id": json.loads(request.data)["intake_id"], "status": "partial",
                    "unresolved_fields": [], "needs_review": True, "demo": False}
        resp = io.BytesIO(json.dumps(body).encode())
        resp.status = status
        resp.__enter__ = lambda s=resp: s
        resp.__exit__ = lambda s, *a: False
        return resp

    def sent_to(self, fragment: str) -> list:
        return [r for r in self.requests if fragment in r.full_url]

    def left_the_building(self) -> list:
        """Requests to anything other than the Jetson itself.

        The kiosk legitimately talks to its own whisper and ollama on 127.0.0.1 at session
        start; those are not the network. Only a non-loopback host counts as the outside.
        """

        return [
            r for r in self.requests
            if urllib.parse.urlsplit(r.full_url).hostname not in ("127.0.0.1", "localhost", "::1")
        ]


def provisioned_settings(tmp_path, monkeypatch, *, enabled: bool) -> tuple[Settings, ScriptedNetwork]:
    """A kiosk with a token file and, optionally, the cloud path switched on.

    The token is a fixture value - nothing here talks to the real service.
    """

    token_file = tmp_path / "kiosk_token"
    token_file.write_text("f" * 64)
    with contextlib.suppress(OSError):  # Windows has no owner-only mode; load_token skips the check
        token_file.chmod(0o600)
    network = ScriptedNetwork()
    monkeypatch.setattr(intake_api_module.urllib.request, "urlopen", network)
    settings = Settings(
        deployment_profile="demo",
        session_store_path=tmp_path / "data" / "kiosk.db",
        handwritten_cloud_ocr=enabled,
        intake_token_path=token_file,
    )
    return settings, network


def walk_to_documents(ws) -> None:
    ws.send_json({"type": "flow.language", "value": "en"})
    _screen(ws)
    ws.send_json({"type": "flow.abha", "value": ""})
    _screen(ws)
    ws.send_json({"type": "flow.who", "value": "self"})
    _screen(ws)
    ws.send_json({"type": "transcript.submit", "text": "stomach pain", "language": "en-IN"})
    for answer in ("two weeks", "four", "no", "no", "no", "no", "I am 30"):
        ws.send_json({"type": "transcript.submit", "text": answer, "language": "en-IN"})
        if _wait_for(ws, "clinical.turn")["data"]["next_question_id"] is None:
            break
    screen = _screen(ws)
    for _ in ayurveda.QUESTIONS:
        if screen.get("stage") != "ayurveda" or screen.get("complete"):
            break
        ws.send_json({"type": "flow.ayurveda", "question_id": screen["question_id"],
                      "value": screen["options"][0]["value"]})
        screen = _screen(ws)
    assert screen["stage"] == "prakriti"
    ws.send_json({"type": "flow.prakriti", "value": "yes"})
    assert _screen(ws)["stage"] == "documents"


# ------------------------------------------------------------------ 1. off by default


def test_with_the_feature_off_nothing_leaves_the_building(tmp_path, monkeypatch) -> None:
    """The default. A session with a scanned page finishes with zero network calls.

    The page is a real held document with a real handle, so the only thing standing between it
    and the upload is the flag. A forged handle here would let this test pass on the strength
    of the handle check instead, and say nothing about the flag - which is what a mutation run
    found the first version of this test doing.
    """

    settings, network = provisioned_settings(tmp_path, monkeypatch, enabled=False)
    outbox = DocumentOutbox(settings.session_store_path.parent / "outbox")
    handle = outbox.hold(b"jpeg", "prescription", "r")
    client = TestClient(create_app(settings))
    with client.websocket_connect("/ws/session") as ws:
        _screen(ws)
        walk_to_documents(ws)
        ws.send_json({"type": "flow.document", "lines": ["Tab Paracetamol 500mg"],
                      "handwritten": True, "outbox_handle": handle})
        _screen(ws)
        ws.send_json({"type": "flow.next"})
        report = _wait_for(ws, "flow.report")["data"]
        ws.send_json({"type": "session.stop"})

    outside = network.left_the_building()
    assert outside == [], (
        "the cloud path was off and something still left the building: "
        + str([r.full_url for r in outside])
    )
    assert "cloud_documents" not in report
    # Held, but never sent: still pending on disk for the day the feature is turned on.
    assert outbox.get(handle).state == "pending"


# ------------------------------------------------------------------ 2. forged handles


def test_a_handle_the_outbox_did_not_issue_is_dropped(tmp_path, monkeypatch) -> None:
    """The handle names a file the kiosk will upload. A client must not get to choose it."""

    settings, network = provisioned_settings(tmp_path, monkeypatch, enabled=True)
    client = TestClient(create_app(settings))
    with client.websocket_connect("/ws/session") as ws:
        _screen(ws)
        walk_to_documents(ws)
        ws.send_json({"type": "flow.document", "lines": ["x"], "handwritten": True,
                      "outbox_handle": "../../etc/passwd"})
        _screen(ws)
        ws.send_json({"type": "flow.next"})
        report = _wait_for(ws, "flow.report")["data"]
        ws.send_json({"type": "session.stop"})

    assert report["documents"][0]["outbox_handle"] is None
    assert network.sent_to("/documents") == [], "a forged handle reached the upload path"


# ------------------------------------------------------------------ 3. the real path


def test_held_pages_are_ingested_then_uploaded_against_the_intake(tmp_path, monkeypatch) -> None:
    settings, network = provisioned_settings(tmp_path, monkeypatch, enabled=True)
    outbox = DocumentOutbox(settings.session_store_path.parent / "outbox")
    handle = outbox.hold(b"\xff\xd8\xff jpeg", "prescription", "33% of 39 lines below 0.7")
    network.script = [
        # The API echoes the intake_id the kiosk chose - which is the session id.
        ("echo-intake-id", 200),
        ({"document_id": "doc-9", "status": "received", "url": None, "demo": False}, 202),
    ]

    client = TestClient(create_app(settings))
    with client.websocket_connect("/ws/session") as ws:
        _screen(ws)
        walk_to_documents(ws)
        ws.send_json({"type": "flow.document", "lines": ["scrawl"], "handwritten": True,
                      "outbox_handle": handle})
        _screen(ws)
        ws.send_json({"type": "flow.next"})
        report = _wait_for(ws, "flow.report")["data"]
        ws.send_json({"type": "session.stop"})

    # Order matters: the intake has to exist before anything can be attached to it.
    outside = network.left_the_building()
    ingest, upload = outside
    assert ingest.full_url.endswith("/api/v1/intakes/ingest")
    sent = json.loads(ingest.data)
    # The contract, or the API files it as unusable and returns intake_id: null.
    assert sent["schema_version"] == "0.2"
    assert sent["fields"]["complaint"] == "abdominal pain"
    # The kiosk picks the intake id and it is the same key a retry would reuse.
    assert sent["intake_id"] == ingest.get_header("Idempotency-key")
    assert ingest.get_header("Authorization") == "Bearer " + "f" * 64
    # ...and the upload is addressed to exactly that id.
    assert upload.full_url.endswith(f"/api/v1/intakes/{sent['intake_id']}/documents")

    cloud = report["cloud_documents"]
    assert cloud["ingest"] == "ok"
    assert cloud["intake_id"] == sent["intake_id"]
    [doc] = cloud["documents"]
    assert doc["state"] == UPLOADED
    assert doc["document_id"] == "doc-9"
    assert outbox.get(handle).state == UPLOADED


def test_an_ambiguous_upload_is_parked_and_a_second_finish_does_not_resend(
    tmp_path, monkeypatch
) -> None:
    """The duplicate-document failure, exercised through the server rather than the outbox alone."""

    settings, network = provisioned_settings(tmp_path, monkeypatch, enabled=True)
    outbox = DocumentOutbox(settings.session_store_path.parent / "outbox")
    handle = outbox.hold(b"jpeg", "prescription", "r")
    network.script = [
        ("echo-intake-id", 200),
        urllib.error.URLError(TimeoutError("read timed out")),  # upload: ambiguous
    ]

    client = TestClient(create_app(settings))
    with client.websocket_connect("/ws/session") as ws:
        _screen(ws)
        walk_to_documents(ws)
        ws.send_json({"type": "flow.document", "lines": ["x"], "handwritten": True,
                      "outbox_handle": handle})
        _screen(ws)
        ws.send_json({"type": "flow.next"})
        report = _wait_for(ws, "flow.report")["data"]
        ws.send_json({"type": "session.stop"})

    [doc] = report["cloud_documents"]["documents"]
    assert doc["state"] == AMBIGUOUS
    uploads_so_far = len(network.sent_to("/documents"))
    assert uploads_so_far == 1

    # A person, or a retry, asks the outbox to submit the same handle again. Nothing is sent.
    from medikiosk.providers.intake_api import IntakeApi

    outbox.submit(IntakeApi("f" * 64, opener=network), "any-intake", [handle])
    assert len(network.sent_to("/documents")) == uploads_so_far, "ambiguous document was resent"


def test_if_ingest_fails_no_document_is_uploaded(tmp_path, monkeypatch) -> None:
    """There is no intake to attach to, so the pages stay held - pending, for a later attempt."""

    settings, network = provisioned_settings(tmp_path, monkeypatch, enabled=True)
    outbox = DocumentOutbox(settings.session_store_path.parent / "outbox")
    handle = outbox.hold(b"jpeg", "prescription", "r")
    network.script = [urllib.error.URLError(ConnectionRefusedError("refused"))]

    client = TestClient(create_app(settings))
    with client.websocket_connect("/ws/session") as ws:
        _screen(ws)
        walk_to_documents(ws)
        ws.send_json({"type": "flow.document", "lines": ["x"], "handwritten": True,
                      "outbox_handle": handle})
        _screen(ws)
        ws.send_json({"type": "flow.next"})
        report = _wait_for(ws, "flow.report")["data"]
        ws.send_json({"type": "session.stop"})

    assert report["cloud_documents"]["ingest"] == "unreachable"
    assert network.sent_to("/documents") == []
    assert outbox.get(handle).state == "pending"
    # And the patient still got their report - the cloud path never blocks the sheet.
    assert report["routing"]["queue"]


def test_a_record_the_api_files_as_unusable_uploads_nothing(tmp_path, monkeypatch) -> None:
    """intake_id: null means no intake exists. Attaching to it 404s, so do not try - and put the
    API's reason on the sheet so the operator can see why the record did not land."""

    settings, network = provisioned_settings(tmp_path, monkeypatch, enabled=True)
    outbox = DocumentOutbox(settings.session_store_path.parent / "outbox")
    handle = outbox.hold(b"jpeg", "prescription", "r")
    network.script = [({
        "intake_id": None, "status": "needs_manual_review", "reason": "unsupported_version",
        "errors": [{"loc": ["schema_version"], "type": "unsupported_version",
                    "msg": "no contract for schema_version None"}],
    }, 200)]

    client = TestClient(create_app(settings))
    with client.websocket_connect("/ws/session") as ws:
        _screen(ws)
        walk_to_documents(ws)
        ws.send_json({"type": "flow.document", "lines": ["x"], "handwritten": True,
                      "outbox_handle": handle})
        _screen(ws)
        ws.send_json({"type": "flow.next"})
        report = _wait_for(ws, "flow.report")["data"]
        ws.send_json({"type": "session.stop"})

    cloud = report["cloud_documents"]
    assert cloud["ingest"] == "unusable"
    assert cloud["reason"] == "unsupported_version"
    assert "schema_version" in str(cloud["errors"])
    assert network.sent_to("/documents") == [], "uploaded against an intake that does not exist"
    assert outbox.get(handle).state == "pending"
