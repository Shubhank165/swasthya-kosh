"""What may leave the kiosk for the hospital's cloud, and what may not.

No test here touches the network: the IntakeApi is constructed against a fake opener, so a
regression that starts transmitting shows up as an assertion rather than as a live record in
somebody's hospital.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_offline_workflow import Driver, clinical_review
from test_offline_workflow import settings as _settings  # noqa: F401

from medikiosk.app import create_app
from medikiosk.kiosk import hospital_sync
from medikiosk.providers.intake_api import Outcome, Response

HOSPITAL = "aiia-delhi"
CONSENT_DOC = {
    "consent_version": "1",
    "purposes": [
        {"code": "history_intake", "required": True, "label": {"en": "Recording your history"}},
        {"code": "hospital_record_linkage", "required": False, "label": {"en": "Linking it"}},
        {"code": "document_processing", "required": False, "label": {"en": "Reading documents"}},
        {"code": "raw_audio_retention", "required": False, "label": {"en": "Keeping your voice"}},
    ],
}
HOSPITALS_DOC = {
    "hospitals": [
        {
            "hospital_id": HOSPITAL,
            "default_language": "hi",
            "departments": [
                {"code": "kayachikitsa", "display_name": "Kayachikitsa"},
                {"code": "cardiology", "display_name": "Cardiology"},
            ],
        }
    ]
}
VERSION_DOC = {"content_version": "q1.3c7b174e850e", "schema_version": "0.2"}


@pytest.fixture
def hospital(settings, monkeypatch, tmp_path):
    """A provisioned kiosk whose every call to the hospital is recorded, not sent."""

    sent: list[tuple[str, dict]] = []
    token = tmp_path / "kiosk_token"
    token.write_text("t" * 64, encoding="ascii")
    settings.handwritten_cloud_ocr = True
    settings.intake_token_path = token

    def fake_send(self, request):
        url = request.full_url
        body = json.loads(request.data) if request.data else {}
        sent.append((url, body))
        if url.endswith("/kiosk/whoami"):
            return Response(Outcome.OK, 200, {"role": "kiosk", "hospital_id": HOSPITAL})
        if url.endswith("/content/consent"):
            return Response(Outcome.OK, 200, CONSENT_DOC)
        if url.endswith("/hospitals"):
            return Response(Outcome.OK, 200, HOSPITALS_DOC)
        if url.endswith("/content/bundle/version"):
            return Response(Outcome.OK, 200, VERSION_DOC)
        if url.endswith("/intakes/ingest"):
            return Response(
                Outcome.OK,
                200,
                {"intake_id": body.get("intake_id"), "status": "complete", "repaired": False},
            )
        raise AssertionError(f"kiosk called an endpoint it has no business calling: {url}")

    monkeypatch.setattr("medikiosk.providers.intake_api.IntakeApi._send", fake_send)
    return sent


def ingested(sent):
    return [body for url, body in sent if url.endswith("/intakes/ingest")]


def test_the_record_is_sent_only_after_the_patient_allows_that_specific_transfer(
    settings, hospital
):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("confirm")
        # Confirming the review does not finalize; it asks the one question that authorizes
        # transmission, on the record the patient has just read.
        assert driver.screen["stage"] == "consent"
        assert driver.screen["question_id"] == "consent.cloud_intake"
        assert not ingested(hospital)

        driver.act("choose", "yes")
        report = driver.report

    assert report["cloud_status"] == "sent"
    assert report["hospital_intake_id"] == report["encounter_id"]
    record = ingested(hospital)[0]
    assert record["hospital_id"] == HOSPITAL
    assert record["schema_version"] == "0.2"
    assert record["status"] == "complete"
    assert record["content_version"] == VERSION_DOC["content_version"]
    # Every field says whether it was answered; nothing is a bare scalar.
    assert all("status" in field for field in record["fields"].values())
    assert record["fields"]["chief_complaint"]["value"] == "abdominal pain"
    assert record["patient_ref"] == {"type": "guest"}


def test_every_answered_field_traces_back_to_the_turn_that_asked_it(settings, hospital):
    """A fact a physician cannot click through to is a fact they cannot check.

    The contract makes `turns` optional, so a record without them validates and is quietly
    unverifiable - which is exactly the failure this asserts against.
    """

    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("confirm")
        driver.act("choose", "yes")

    record = ingested(hospital)[0]
    turns = {turn["turn_id"]: turn for turn in record["turns"]}
    assert turns, "no evidence trail was sent"

    complaint = record["fields"]["chief_complaint"]
    turn = turns[complaint["source_turn"]]
    assert turn["bound_field"] == "chief_complaint"
    assert turn["question_id"] == "ask_complaint"
    assert turn["asked_text"], "the question as actually put to the patient"
    assert turn["resolved"] is True

    # A tapped answer is not a transcript: the voice keys are present and null, matching what
    # the hospital's own app sends, rather than claiming an option label was spoken.
    typed = [t for t in record["turns"] if t["transcript"] is None]
    assert typed and all(t["asr_confidence"] is None for t in typed)
    assert all({"transcript", "asr_confidence"} <= set(t) for t in record["turns"])

    # Each of the 58 Prakriti items is on the record, but none of them claims to be the source
    # of the constitution: that is scored from all of them together.
    assert all(t["bound_field"] != "prakriti_self_report" for t in record["turns"])


def test_the_record_says_which_kiosk_took_it_and_what_was_running(settings, hospital):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("confirm")
        driver.act("choose", "yes")

    record = ingested(hospital)[0]
    # Null here is the hospital app's signature; a kiosk sending null is indistinguishable
    # from it, and two kiosks in one OPD become impossible to tell apart.
    assert record["kiosk_id"]
    assert record["engine_version"].startswith("medikiosk-")


def test_a_corrected_answer_keeps_both_turns_and_points_at_the_one_that_stood(settings, hospital):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("edit", "ask_duration")
        driver.act("answer", "five days")
        driver.act("confirm")
        driver.act("choose", "yes")

    record = ingested(hospital)[0]
    duration_turns = [t for t in record["turns"] if t["question_id"] == "ask_duration"]
    assert len(duration_turns) == 2, "the correction and what it replaced are both evidence"
    stood = record["fields"]["duration"]["source_turn"]
    assert stood == max(t["turn_id"] for t in duration_turns)
    assert record["fields"]["duration"]["value"] == "five days"


def test_a_refused_transfer_completes_the_intake_and_sends_nothing(settings, hospital):
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("confirm")
        driver.act("choose", "no")
        report = driver.report

    assert report["completion"] == "saved_local"
    assert report["cloud_status"] == "declined_by_patient"
    assert "hospital_intake_id" not in report
    assert report["queue_entry"]["number"], "a refusal must still get the patient a token"
    assert not ingested(hospital)


def test_a_failed_export_never_costs_the_patient_their_finished_intake(
    settings, hospital, monkeypatch
):
    def unreachable(self, request):
        if request.full_url.endswith("/intakes/ingest"):
            return Response(Outcome.UNREACHABLE, detail="never connected")
        return original(self, request)

    from medikiosk.providers.intake_api import IntakeApi

    original = IntakeApi._send
    monkeypatch.setattr(IntakeApi, "_send", unreachable)

    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("confirm")
        driver.act("choose", "yes")
        report = driver.report

    assert report["completion"] == "saved_local"
    assert report["cloud_status"] == "failed:unreachable"
    assert report["queue_entry"]["number"]


def test_an_unprovisioned_kiosk_never_asks_about_transfer(settings, monkeypatch):
    settings.handwritten_cloud_ocr = True
    settings.intake_token_path = Path("nonexistent") / "kiosk_token"

    def no_network(*args, **kwargs):
        raise AssertionError("An unprovisioned kiosk attempted a network call")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("confirm")
        assert driver.report["cloud_status"] == "not_requested"


def test_hospital_configuration_is_cached_so_the_next_intake_runs_offline(settings, hospital):
    cache = settings.session_store_path.parent / "hospital"
    with TestClient(create_app(settings)):
        pass
    cached = hospital_sync.load(cache)

    assert hospital_sync.consent_version(cached) == "1"
    assert hospital_sync.content_version(cached) == VERSION_DOC["content_version"]
    assert hospital_sync.department_code(cached, HOSPITAL, "Cardiology") == "cardiology"
    # A queue with no department at this hospital stays unset rather than being guessed at.
    assert hospital_sync.department_code(cached, HOSPITAL, "Dentistry") is None
    # Our purpose, in the hospital's own words, for showing beside our notice.
    assert [p["code"] for p in hospital_sync.hospital_purposes(cached, "cloud_intake")] == [
        "history_intake",
        "hospital_record_linkage",
    ]
    # Nothing maps onto keeping the patient's voice: the kiosk never retains audio.
    assert "raw_audio_retention" not in str(hospital_sync.PURPOSE_MAP)


def test_a_kiosk_that_cannot_reach_the_cloud_still_runs_the_whole_intake(settings, monkeypatch):
    """No internet at startup is the normal case, not a failure to recover from."""

    token = settings.session_store_path.parent / "kiosk_token"
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text("t" * 64, encoding="ascii")
    settings.handwritten_cloud_ocr = True
    settings.intake_token_path = token
    monkeypatch.setattr(
        "medikiosk.providers.intake_api.IntakeApi._send",
        lambda self, request: Response(Outcome.UNREACHABLE, detail="never connected"),
    )
    with TestClient(create_app(settings)) as client, client.websocket_connect("/ws/session") as ws:
        driver = Driver(ws)
        clinical_review(driver)
        driver.act("confirm")
        # Nothing knows which hospital this token writes into, so nothing is asked and
        # nothing is sent - but the patient still finishes and still gets a token.
        assert driver.report["completion"] == "saved_local"
        assert driver.report["cloud_status"] == "unreachable"
        assert driver.report["queue_entry"]["number"]
