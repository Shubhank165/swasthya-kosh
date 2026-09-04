"""The Pub/Sub push endpoint — §6, §11.

The worker is a second deployment of the same image, and this is its entry
point. What is asserted here is almost entirely about **status codes**, because
on a push subscription the status code *is* the retry policy:

- `204` acknowledges. Pub/Sub stops.
- `5xx` retries with backoff.

Get that backwards and either a poison message pins a worker forever, or a
patient's prescription is dropped silently. Neither shows up in a log anybody
reads until somebody asks why a document never processed.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from typing import Any

import pytest

from tests.conftest import HOSPITAL_ID, KIOSK_HEADERS, STAFF_HEADERS

PUSH_TOKEN = "push-secret-for-tests"


@pytest.fixture
def worker_client(engine: Any, settings: Any, still_clock: Any) -> Iterator[Any]:
    """A client for the *worker* deployment: push route on, token required."""
    from fastapi.testclient import TestClient

    from app import db as db_module
    from app.api import auth, deps
    from app.core import config as config_module
    from app.core.content import get_clinical_content
    from app.core.ids import SequentialIdFactory
    from app.events.bus import reset_event_bus
    from app.main import create_app

    worker_settings = settings.model_copy(
        update={"pubsub_push_enabled": True, "pubsub_push_token": PUSH_TOKEN}
    )

    config_module.get_settings.cache_clear()
    get_clinical_content.cache_clear()
    reset_event_bus()
    deps.reset_providers()

    db_module.configure(engine)
    original = config_module.get_settings
    config_module.get_settings = lambda: worker_settings  # type: ignore[assignment]
    # `main` imported the function by name, so the module attribute above is not
    # the reference `create_app` calls. Patching only one of the two leaves the
    # router registration reading the real environment.
    import app.main as main_module

    main_original = main_module.get_settings
    main_module.get_settings = lambda: worker_settings  # type: ignore[assignment]

    application = create_app()
    application.dependency_overrides[deps.get_settings_dep] = lambda: worker_settings
    application.dependency_overrides[auth.auth_settings] = lambda: worker_settings
    application.dependency_overrides[deps.get_clock] = lambda: still_clock
    application.dependency_overrides[deps.get_ids] = SequentialIdFactory

    with TestClient(application) as client:
        yield client

    config_module.get_settings = original  # type: ignore[assignment]
    main_module.get_settings = main_original  # type: ignore[assignment]
    config_module.get_settings.cache_clear()
    get_clinical_content.cache_clear()
    reset_event_bus()
    deps.reset_providers()


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """What Pub/Sub actually posts."""
    return {
        "message": {
            "data": base64.b64encode(json.dumps(payload).encode()).decode(),
            "messageId": "1",
            "publishTime": "2026-09-03T10:21:05Z",
        },
        "subscription": "projects/p/subscriptions/medikiosk-documents",
    }


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {PUSH_TOKEN}"}


@pytest.fixture
def uploaded(
    worker_client: Any, kiosk_payload: dict[str, Any], ocr_images: dict[str, bytes]
) -> str:
    """An intake with an unprocessed document waiting on it."""
    ingest = worker_client.post(
        "/api/v1/intakes/ingest", json=kiosk_payload, headers=KIOSK_HEADERS
    )
    assert ingest.status_code == 200, ingest.text
    intake_id = ingest.json()["intake_id"]
    upload = worker_client.post(
        f"/api/v1/intakes/{intake_id}/documents",
        files={"file": ("p.jpg", ocr_images["prescription_clean"], "image/jpeg")},
        headers=KIOSK_HEADERS,
    )
    assert upload.status_code == 202, upload.text
    return str(upload.json()["document_id"])


class TestTheRouteExistsOnlyOnTheWorker:
    def test_the_public_api_does_not_publish_it(self, app_client: Any) -> None:
        """`PUBSUB_PUSH_ENABLED` is off on the API deployment.

        Absent, rather than present and guarded: an endpoint that does not exist
        cannot be probed, and this one drives work on behalf of no user.
        """
        response = app_client.post("/api/v1/worker/documents", json={})
        assert response.status_code == 404

    def test_the_worker_does_publish_it(self, worker_client: Any) -> None:
        response = worker_client.post(
            "/api/v1/worker/documents", json={}, headers=_auth()
        )
        assert response.status_code != 404

    def test_it_stays_out_of_the_openapi_schema(self, worker_client: Any) -> None:
        """Not part of the published API. Nothing but Pub/Sub calls it."""
        schema = worker_client.get("/openapi.json").json()
        assert "/api/v1/worker/documents" not in schema["paths"]


class TestTheSharedSecret:
    def test_a_push_without_the_token_is_refused(
        self, worker_client: Any, uploaded: str
    ) -> None:
        response = worker_client.post(
            "/api/v1/worker/documents",
            json=_envelope({"hospital_id": HOSPITAL_ID, "document_id": uploaded}),
        )
        assert response.status_code == 403

    def test_a_push_with_the_wrong_token_is_refused(
        self, worker_client: Any, uploaded: str
    ) -> None:
        response = worker_client.post(
            "/api/v1/worker/documents",
            json=_envelope({"hospital_id": HOSPITAL_ID, "document_id": uploaded}),
            headers={"Authorization": "Bearer not-the-token"},
        )
        assert response.status_code == 403


class TestItActuallyProcessesTheDocument:
    def test_the_document_is_read(
        self, worker_client: Any, uploaded: str, kiosk_payload: dict[str, Any]
    ) -> None:
        """The claim the endpoint exists for.

        The same `DocumentService.process` the local background task calls, so
        the cloud path and the laptop path cannot produce different records.
        """
        response = worker_client.post(
            "/api/v1/worker/documents",
            json=_envelope({"hospital_id": HOSPITAL_ID, "document_id": uploaded}),
            headers=_auth(),
        )
        assert response.status_code == 204, response.text

        intake_id = kiosk_payload["intake_id"]
        documents = worker_client.get(
            f"/api/v1/intakes/{intake_id}/documents", headers=STAFF_HEADERS
        ).json()
        assert [d["status"] for d in documents] == ["processed"]

    def test_a_redelivery_does_not_read_the_document_twice(
        self, worker_client: Any, uploaded: str, kiosk_payload: dict[str, Any]
    ) -> None:
        """Pub/Sub delivers at least once, so this is expected, not exceptional.

        Without the guard in `DocumentService.process` a second delivery
        duplicated every extracted line — which surfaces on the report as five
        medicines where the prescription printed five, and as a contradiction
        against a medicine the patient is taking exactly once.
        """
        push = _envelope({"hospital_id": HOSPITAL_ID, "document_id": uploaded})
        for _ in range(3):
            assert (
                worker_client.post(
                    "/api/v1/worker/documents", json=push, headers=_auth()
                ).status_code
                == 204
            )

        intake_id = kiosk_payload["intake_id"]
        record = worker_client.get(
            f"/api/v1/intakes/{intake_id}", headers=STAFF_HEADERS
        ).json()
        document_facts = [f for f in record["facts"] if f["channel"] == "document"]
        assert len(document_facts) == len({f["field_id"] for f in document_facts})

        # And on the report: the drug history lists each printed line once.
        # (The same text also appears under INFORMATION CONFLICTS, which is the
        # point of that section, so the count is taken per section.)
        report = worker_client.get(
            f"/api/v1/intakes/{intake_id}/report",
            params={"language": "en"},
            headers=STAFF_HEADERS,
        ).json()["text"]
        drug_history = report.split("DRUG HISTORY")[1].split("ALLERGIES")[0]
        assert drug_history.count("Metformin 500 mg BD for 30 days") == 1
        assert drug_history.count("Omeprazole 20 mg OD for 14 days") == 1

    def test_a_bare_event_body_works_too(
        self, worker_client: Any, uploaded: str
    ) -> None:
        """What a `curl` during an incident sends.

        Being able to replay one message by hand at 2am is worth the six lines
        that accept it.
        """
        response = worker_client.post(
            "/api/v1/worker/documents",
            json={"hospital_id": HOSPITAL_ID, "document_id": uploaded},
            headers=_auth(),
        )
        assert response.status_code == 204

    def test_attributes_are_read_when_the_payload_carries_none(
        self, worker_client: Any, uploaded: str
    ) -> None:
        response = worker_client.post(
            "/api/v1/worker/documents",
            json={
                "message": {
                    "attributes": {
                        "hospital_id": HOSPITAL_ID,
                        "document_id": uploaded,
                    },
                    "messageId": "2",
                }
            },
            headers=_auth(),
        )
        assert response.status_code == 204


class TestTheRetryPolicy:
    """The status code is the policy. Both directions are wrong differently."""

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"message": {}},
            {"message": {"data": "not-base64!!"}},
            {"message": {"data": base64.b64encode(b"not json").decode()}},
            {"message": {"data": base64.b64encode(b'["a list"]').decode()}},
            {"hospital_id": "aiia-delhi"},
        ],
        ids=["empty", "no-data", "bad-base64", "not-json", "not-an-object", "no-document"],
    )
    def test_an_undecodable_message_is_acknowledged_rather_than_retried(
        self, worker_client: Any, body: dict[str, Any]
    ) -> None:
        """Redelivering rubbish produces the same rubbish.

        A poison message that never acks is a subscription that never drains,
        and the next real document queues behind it.
        """
        response = worker_client.post(
            "/api/v1/worker/documents", json=body, headers=_auth()
        )
        assert response.status_code == 204, response.text

    def test_an_unknown_document_is_acknowledged_rather_than_retried(
        self, worker_client: Any
    ) -> None:
        """A 404 is permanent. The document is not going to appear."""
        response = worker_client.post(
            "/api/v1/worker/documents",
            json=_envelope(
                {"hospital_id": HOSPITAL_ID, "document_id": "doc_does_not_exist"}
            ),
            headers=_auth(),
        )
        assert response.status_code == 204

    def test_a_transient_failure_asks_to_be_retried(
        self, worker_client: Any, uploaded: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A provider outage genuinely can succeed later, so it must not ack.

        Acknowledging here drops a patient's prescription with nothing on the
        record to say it happened.
        """
        from app.services.documents import DocumentService

        async def _boom(self: Any, **kwargs: Any) -> Any:
            raise RuntimeError("the OCR provider is unreachable")

        from fastapi.testclient import TestClient

        monkeypatch.setattr(DocumentService, "process", _boom)
        # A second client over the same app: the exception has to reach the
        # transport as a 500 rather than being re-raised into the test, because
        # the 500 is the thing being asserted.
        with TestClient(worker_client.app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/worker/documents",
                json=_envelope({"hospital_id": HOSPITAL_ID, "document_id": uploaded}),
                headers=_auth(),
            )
        assert response.status_code >= 500
