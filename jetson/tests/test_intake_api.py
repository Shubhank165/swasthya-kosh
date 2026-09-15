"""The intake API client, and the one distinction that matters: may this send be retried?

The document endpoint is not idempotent. A retry after a send that actually landed puts a second
copy of a clinical document on a patient's record, and nothing upstream merges them. So every
failure has to be classified by whether the bytes could have reached the server, and these tests
exist to pin that classification rather than the happy path.
"""

from __future__ import annotations

import io
import json
import socket
import ssl
import urllib.error
from pathlib import Path

import pytest

from medikiosk.providers.intake_api import IntakeApi, Outcome, kiosk_envelope, redacted

TOKEN = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


class FakeResponse(io.BytesIO):
    def __init__(self, payload: dict, status: int = 200) -> None:
        super().__init__(json.dumps(payload).encode("utf-8"))
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def api_that(raiser) -> IntakeApi:
    """A client whose transport always fails in one specific way."""

    def opener(request, timeout=None):
        raise raiser

    return IntakeApi(TOKEN, opener=opener)


def api_returning(payload: dict, status: int = 200) -> tuple[IntakeApi, list]:
    sent = []

    def opener(request, timeout=None):
        sent.append(request)
        return FakeResponse(payload, status)

    return IntakeApi(TOKEN, opener=opener), sent


# ------------------------------------------------------------------ retry taxonomy


@pytest.mark.parametrize(
    "reason",
    [
        socket.gaierror("name resolution failed"),
        ConnectionRefusedError("refused"),
        ssl.SSLError("handshake failed"),
    ],
)
def test_never_connected_is_safe_to_retry(reason) -> None:
    """The bytes never left the building, so nothing can have been recorded upstream."""

    response = api_that(urllib.error.URLError(reason)).upload_document(
        "intake-1", Path(__file__), "prescription"
    )
    assert response.outcome is Outcome.UNREACHABLE
    assert response.safe_to_retry is True


@pytest.mark.parametrize(
    "reason",
    [
        TimeoutError("timed out"),
        TimeoutError("timed out"),
        ConnectionResetError("reset by peer"),
        BrokenPipeError("broken pipe"),
    ],
)
def test_connected_then_lost_is_never_retried(reason) -> None:
    """The server may already have accepted the document. Retrying would duplicate it."""

    response = api_that(urllib.error.URLError(reason)).upload_document(
        "intake-1", Path(__file__), "prescription"
    )
    assert response.outcome is Outcome.AMBIGUOUS
    assert response.safe_to_retry is False


def test_an_unrecognised_transport_failure_is_treated_as_ambiguous() -> None:
    """When it cannot be told which side of the line a failure falls, assume the dangerous one.

    Guessing "unreachable" for an unknown error is how a duplicate clinical document is created.
    """

    response = api_that(urllib.error.URLError(RuntimeError("something new"))).upload_document(
        "intake-1", Path(__file__)
    )
    assert response.outcome is Outcome.AMBIGUOUS
    assert response.safe_to_retry is False


def test_a_server_error_is_definitive_not_retryable() -> None:
    """An HTTP status means the server answered - the outcome is known, not in doubt."""

    error = urllib.error.HTTPError(
        "u", 401, "unauthorized", {},
        io.BytesIO(b'{"code":"unauthorized","message":"unrecognised service token"}'),
    )
    response = api_that(error).whoami()
    assert response.outcome is Outcome.REJECTED
    assert response.status == 401
    assert response.safe_to_retry is False
    assert response.body["code"] == "unauthorized"


def test_a_direct_timeout_is_ambiguous() -> None:
    response = api_that(TimeoutError("no answer")).upload_document("intake-1", Path(__file__))
    assert response.outcome is Outcome.AMBIGUOUS


# ------------------------------------------------------------------ requests


def test_every_call_carries_the_bearer_token() -> None:
    api, sent = api_returning({"role": "kiosk", "hospital_id": "aiia-delhi"})
    assert api.whoami().ok
    assert sent[0].get_header("Authorization") == f"Bearer {TOKEN}"


def test_ingest_sends_an_idempotency_key() -> None:
    """Retrying ingest with the same key returns the original intake and creates nothing."""

    api, sent = api_returning({"intake_id": "abc"})
    api.ingest({"patient": "x"}, idempotency_key="fixed-key")
    # urllib normalises header names with str.capitalize(), so it stores "Idempotency-key".
    # HTTP header names are case-insensitive, so it goes out correctly - but look it up the way
    # urllib stores it or this assertion silently reads None and passes nothing.
    assert sent[0].get_header("Idempotency-key") == "fixed-key"

    api2, sent2 = api_returning({"intake_id": "abc"})
    api2.ingest({"patient": "x"})
    assert sent2[0].get_header("Idempotency-key"), "a key must always be sent"


def test_upload_is_multipart_with_the_kind(tmp_path) -> None:
    image = tmp_path / "slip.jpg"
    image.write_bytes(b"\xff\xd8\xff jpeg bytes")
    api, sent = api_returning({"document_id": "doc-1"}, status=202)

    assert api.upload_document("intake-9", image, "prescription").ok
    request = sent[0]
    assert "/api/v1/intakes/intake-9/documents" in request.full_url
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'name="kind"' in request.data
    assert b"prescription" in request.data
    assert b"\xff\xd8\xff jpeg bytes" in request.data


def test_an_unknown_kind_is_sent_as_other_rather_than_failing(tmp_path) -> None:
    """A mislabelled document still belongs on the record; refusing it locally loses it."""

    image = tmp_path / "slip.jpg"
    image.write_bytes(b"jpeg")
    api, sent = api_returning({"document_id": "doc-1"}, status=202)
    api.upload_document("intake-9", image, "handwritten-scrawl")
    assert b"other" in sent[0].data


def test_path_b_sends_extraction_without_the_image() -> None:
    """The whole point of Path B: the image never leaves the building."""

    api, sent = api_returning({"document_id": "doc-2"}, status=201)
    api.post_results("intake-9", {"lines": ["Paracetamol 500mg"]})
    assert "/documents/results" in sent[0].full_url
    assert b"Paracetamol" in sent[0].data
    assert sent[0].get_header("Content-type") == "application/json"


# ------------------------------------------------------------------ the token


def test_the_token_is_never_rendered_in_full() -> None:
    """A debug line must not be able to leak a live credential into a log or a transcript."""

    shown = redacted(TOKEN)
    assert TOKEN not in shown
    assert "ending cdef" in shown
    assert redacted("") == "<none>"


# ------------------------------------------------------------------ the envelope


def test_the_envelope_carries_the_contract_version_and_our_own_intake_id() -> None:
    """Without schema_version the API files the record as unusable and returns intake_id: null,
    and nothing can be attached to it. Found the hard way against the live deploy."""

    env = kiosk_envelope({"clinical": {"complaint": "abdominal pain"}}, "abc-123")
    assert env["schema_version"] == "0.2"
    assert env["intake_id"] == "abc-123"
    assert env["fields"]["complaint"] == "abdominal pain"


def test_the_envelope_sends_only_bound_values() -> None:
    """The API refuses a payload that carries a value for an unresolved field.

    Our report lists the questions the patient never answered under `not_established`; sending
    that list as a field is precisely "a value for an unresolved field", and the live deploy
    rejected it as repair_failed. Empty findings, empty lists and generated_at were the other
    three of the four errors.
    """

    report = {
        "clinical": {
            "complaint": "chest pain", "severity": 7, "duration": None,
            "findings": {"fever": False, "breathlessness": True},
            "medications": [], "allergies": ["penicillin"],
            "not_established": ["vomiting", "age_years"],
        },
        "patient": {"language": "hi", "reported_by": "self", "abha_last4": "1234"},
        "routing": {"queue": "Cardiology", "priority": "URGENT"},
        "red_flags": [{"rule_id": "RF_CHEST_PAIN"}],
        "generated_at": "2026-09-12T00:00:00Z",
    }
    fields = kiosk_envelope(report, "id")["fields"]
    assert fields == {
        "complaint": "chest pain", "severity": 7,
        "fever": False, "breathlessness": True,
        "allergies": ["penicillin"],
        "language": "hi", "reported_by": "self", "abha_last4": "1234",
        "queue": "Cardiology", "priority": "URGENT",
        "red_flags": ["RF_CHEST_PAIN"],
    }
    assert "not_established" not in fields
    assert "generated_at" not in fields
    assert "medications" not in fields, "an empty list is an unanswered question, not an answer"
    assert "duration" not in fields
    # The full ABHA never travels; only the last four the sheet already shows.
    assert "12345678901234" not in str(fields)


def test_the_envelope_survives_a_bare_report() -> None:
    assert kiosk_envelope({}, "id")["fields"] == {}
