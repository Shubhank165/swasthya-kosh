"""Replay protection — §13.7.

**The same intake submitted twice produces one intake.**

The Jetson sits on a hospital LAN and the LAN drops. When the device retries,
the retry has to be a no-op that returns the original answer — not a second
patient in the worklist, and not a clobber of a value staff have corrected since
the first submission.

Two mechanisms, tested separately because they fail separately:

1. `Idempotency-Key`. The device sends one; the same key replays the stored
   response and runs nothing.
2. The intake id itself. A retry sent *without* the header is still a retry —
   the kiosk's `intake_id` identifies the interview — and must not become a
   primary key violation the device reads as a server error.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import KIOSK_HEADERS, STAFF_HEADERS

KEY = {"Idempotency-Key": "kiosk-aiia-01:submit:0007"}


def _post(client: Any, payload: dict[str, Any], **extra: str) -> Any:
    return client.post(
        "/api/v1/intakes/ingest", json=payload, headers={**KIOSK_HEADERS, **extra}
    )


def _worklist_size(client: Any) -> int:
    response = client.get("/api/v1/worklist", headers=STAFF_HEADERS)
    assert response.status_code == 200, response.text
    return int(response.json()["total"])


class TestTheKeyReplaysTheResponse:
    def test_the_same_key_returns_the_same_body(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        first = _post(app_client, kiosk_payload, **KEY)
        second = _post(app_client, kiosk_payload, **KEY)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json() == second.json()

    def test_the_same_key_writes_one_intake(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """The claim the whole mechanism exists for."""
        _post(app_client, kiosk_payload, **KEY)
        _post(app_client, kiosk_payload, **KEY)
        _post(app_client, kiosk_payload, **KEY)
        assert _worklist_size(app_client) == 1

    def test_a_replay_writes_no_second_set_of_facts(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """Duplicated facts would show as a patient who answered twice.

        Worse than a duplicated row: the contradiction detector would compare
        the record against itself.
        """
        first = _post(app_client, kiosk_payload, **KEY)
        intake_id = first.json()["intake_id"]
        before = app_client.get(
            f"/api/v1/intakes/{intake_id}", headers=STAFF_HEADERS
        ).json()

        _post(app_client, kiosk_payload, **KEY)
        after = app_client.get(
            f"/api/v1/intakes/{intake_id}", headers=STAFF_HEADERS
        ).json()

        assert len(after["facts"]) == len(before["facts"])
        assert after["contradictions"] == before["contradictions"]


class TestAReusedKeyWithADifferentBody:
    def test_it_is_a_conflict_rather_than_the_wrong_stored_answer(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """A client bug, not a retry.

        Serving the stored response here would answer a question about one
        patient with a record about another, which is the worst thing this
        mechanism could do.
        """
        _post(app_client, kiosk_payload, **KEY)
        different = {
            **kiosk_payload,
            "intake_id": "8d1d8b0e-3d6f-4a52-9b1a-2f0a0c0d0e77",
        }
        response = _post(app_client, different, **KEY)
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "idempotency_conflict"

    def test_the_conflicting_request_wrote_nothing(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        _post(app_client, kiosk_payload, **KEY)
        _post(
            app_client,
            {**kiosk_payload, "intake_id": "8d1d8b0e-3d6f-4a52-9b1a-2f0a0c0d0e77"},
            **KEY,
        )
        assert _worklist_size(app_client) == 1

    def test_key_order_in_the_body_is_not_a_different_body(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """JSON objects are unordered; a serialiser change is not a new request."""
        first = _post(app_client, kiosk_payload, **KEY)
        reordered = dict(reversed(list(kiosk_payload.items())))
        second = _post(app_client, reordered, **KEY)
        assert second.status_code == 200, second.text
        assert second.json() == first.json()


class TestARetryWithNoKeyAtAll:
    """The device that did not send the header, or lost it in a proxy.

    `intake_id` is generated once per interview on the Jetson, so a second
    submission carrying the same one is the same interview by definition.
    """

    def test_it_is_accepted_rather_than_erroring(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        first = _post(app_client, kiosk_payload)
        second = _post(app_client, kiosk_payload)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert second.json()["intake_id"] == first.json()["intake_id"]

    def test_it_writes_one_intake(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        _post(app_client, kiosk_payload)
        _post(app_client, kiosk_payload)
        assert _worklist_size(app_client) == 1

    def test_it_does_not_overwrite_a_correction_made_since(
        self, app_client: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """A physician verified a field; the kiosk's stuck outbox flushes.

        The replay must return the state as it now stands and change nothing. A
        submission that reset a verified field to its original value would undo
        a clinician's work with no record of having done so.
        """
        first = _post(app_client, kiosk_payload)
        intake_id = first.json()["intake_id"]
        app_client.post(
            f"/api/v1/intakes/{intake_id}/verify",
            json={},
            headers={
                "X-User-Id": "dr-sharma",
                "X-User-Role": "physician",
                "X-Hospital-Id": "aiia-delhi",
            },
        )
        before = app_client.get(
            f"/api/v1/intakes/{intake_id}", headers=STAFF_HEADERS
        ).json()
        verified_before = [f["field_id"] for f in before["facts"] if f["physician_verified"]]
        assert verified_before, "nothing was verified; the test proves nothing"

        _post(app_client, kiosk_payload)

        after = app_client.get(
            f"/api/v1/intakes/{intake_id}", headers=STAFF_HEADERS
        ).json()
        assert [
            f["field_id"] for f in after["facts"] if f["physician_verified"]
        ] == verified_before


class TestTheStoreNamespace:
    """A key is client-supplied, so the store must not be one flat namespace.

    Tested against the store rather than over HTTP: producing the collision over
    the API would need two hospitals to submit the same kiosk `intake_id`, which
    is a contrivance. The property that matters is what goes into the lookup
    predicate — the hospital and the endpoint, alongside the key itself.
    """

    @pytest.fixture
    def records(self) -> Any:
        from datetime import UTC, datetime

        from app.core.idempotency import IdempotencyRecord

        def make(body: dict[str, Any]) -> IdempotencyRecord:
            return IdempotencyRecord(
                key="shared-key",
                endpoint="POST /api/v1/intakes/ingest",
                request_fingerprint="same",
                response_body=body,
                status_code=200,
                created_at=datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
            )

        return make

    async def test_one_hospitals_key_is_invisible_to_another(
        self, session: Any, records: Any
    ) -> None:
        from app.repositories.consent import SqlIdempotencyStore
        from tests.conftest import HOSPITAL_ID, OTHER_HOSPITAL_ID

        ours = SqlIdempotencyStore(session, hospital_id=HOSPITAL_ID)
        theirs = SqlIdempotencyStore(session, hospital_id=OTHER_HOSPITAL_ID)

        await ours.put(records({"intake_id": "ours"}))

        assert (await ours.get("shared-key", "POST /api/v1/intakes/ingest")) is not None
        assert (await theirs.get("shared-key", "POST /api/v1/intakes/ingest")) is None

    async def test_a_key_stored_for_one_endpoint_does_not_replay_into_another(
        self, session: Any, records: Any
    ) -> None:
        """A device that reuses a counter across two calls must not be handed
        one call's answer for the other."""
        from app.repositories.consent import SqlIdempotencyStore
        from tests.conftest import HOSPITAL_ID

        store = SqlIdempotencyStore(session, hospital_id=HOSPITAL_ID)
        await store.put(records({"intake_id": "ours"}))

        assert (await store.get("shared-key", "POST /api/v1/intakes/ingest")) is not None
        assert (await store.get("shared-key", "POST /api/v1/consent")) is None
