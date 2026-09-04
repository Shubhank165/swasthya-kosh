"""Where an uploaded document's OCR work goes — §6, §11.

Two dispatch shapes and one call site. The tests that matter here are the ones
about what the two shapes have in common, because that is what stops the laptop
demo and the cloud deployment producing different records from the same
photograph:

- both end at `DocumentService.process`;
- the message carries identifiers and nothing clinical;
- a failure to queue is a failure to upload, not a silent drop.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from app.adapters.queue.dispatch import (
    InlineDispatcher,
    PubSubDispatcher,
    _process_quietly,
    build_dispatcher,
)
from app.core.config import Settings


class FakeBackground:
    """Stands in for FastAPI's `BackgroundTasks`."""

    def __init__(self) -> None:
        self.tasks: list[tuple[Any, tuple[Any, ...]]] = []

    def add_task(self, func: Any, *args: Any) -> None:
        self.tasks.append((func, args))


class FakeService:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail = fail

    async def process(self, *, hospital_id: str, document_id: str) -> None:
        self.calls.append((hospital_id, document_id))
        if self._fail is not None:
            raise self._fail


class FakeFuture:
    def __init__(self, message_id: str = "msg-1") -> None:
        self._id = message_id

    def result(self, timeout: float | None = None) -> str:
        return self._id


class FakePublisher:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.published: list[tuple[str, bytes, dict[str, str]]] = []
        self._fail = fail

    def topic_path(self, project: str, topic: str) -> str:
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic: str, data: bytes, **attributes: str) -> FakeFuture:
        if self._fail is not None:
            raise self._fail
        self.published.append((topic, data, attributes))
        return FakeFuture()


@pytest.fixture
def publisher(monkeypatch: pytest.MonkeyPatch) -> FakePublisher:
    fake = FakePublisher()
    monkeypatch.setattr(
        "app.adapters.queue.dispatch._publisher_client", lambda: fake
    )
    return fake


class TestTheInlineDispatcher:
    async def test_it_schedules_the_work_rather_than_doing_it(self) -> None:
        """The upload response must not wait on a model.

        The patient has already answered the questions and gone to sit down.
        `dispatch` returning before OCR has run is the whole point.
        """
        background = FakeBackground()
        service = FakeService()
        dispatcher = InlineDispatcher(background, service)

        await dispatcher.dispatch(
            hospital_id="h1", intake_id="i1", document_id="d1"
        )

        assert service.calls == []
        assert len(background.tasks) == 1

    async def test_the_scheduled_task_processes_that_document(self) -> None:
        background = FakeBackground()
        service = FakeService()
        await InlineDispatcher(background, service).dispatch(
            hospital_id="h1", intake_id="i1", document_id="d1"
        )

        func, args = background.tasks[0]
        await func(*args)
        assert service.calls == [("h1", "d1")]

    async def test_a_provider_outage_leaves_the_document_unread_not_the_upload_failed(
        self,
    ) -> None:
        """`_process_quietly` swallows, and that is deliberate.

        By the time this runs the response has gone out and the image is stored.
        Raising here would surface nowhere useful; the document stays unread and
        the report says so, which is the honest state. The failure the kiosk
        must never see is one that makes it re-send a photograph that arrived.
        """
        service = FakeService(fail=RuntimeError("provider down"))
        await _process_quietly(service, "h1", "d1")
        assert service.calls == [("h1", "d1")]


class TestThePubSubDispatcher:
    async def test_it_publishes_to_the_configured_topic(
        self, publisher: FakePublisher
    ) -> None:
        dispatcher = PubSubDispatcher(project_id="proj", topic="docs")
        await dispatcher.dispatch(
            hospital_id="h1", intake_id="i1", document_id="d1"
        )

        topic, _, _ = publisher.published[0]
        assert topic == "projects/proj/topics/docs"

    async def test_the_message_carries_identifiers_and_nothing_else(
        self, publisher: FakePublisher
    ) -> None:
        """The load-bearing privacy assertion.

        A Pub/Sub message is retained for days, is readable by anyone with
        subscriber rights, and is copied into a dead-letter topic when it fails.
        None of those is a place a prescription belongs — so the body is three
        ids and the worker re-reads everything else under the tenant scope it
        names.
        """
        dispatcher = PubSubDispatcher(project_id="proj", topic="docs")
        await dispatcher.dispatch(
            hospital_id="h1", intake_id="i1", document_id="d1"
        )

        _, data, attributes = publisher.published[0]
        payload = json.loads(data.decode("utf-8"))
        assert set(payload) == {"hospital_id", "intake_id", "document_id"}
        assert set(attributes) == {"hospital_id", "intake_id", "document_id"}

    async def test_the_body_decodes_the_way_the_worker_reads_it(
        self, publisher: FakePublisher
    ) -> None:
        """Producer and consumer agree, checked rather than assumed.

        `app.api.v1.worker._decode` base64-decodes `message.data` and expects a
        JSON object with `document_id`. This reproduces that envelope around
        what the dispatcher actually published, so a change to either side
        breaks here rather than in production.
        """
        from app.api.v1.worker import _decode

        dispatcher = PubSubDispatcher(project_id="proj", topic="docs")
        await dispatcher.dispatch(
            hospital_id="h1", intake_id="i1", document_id="d1"
        )
        _, data, attributes = publisher.published[0]

        envelope = {
            "message": {
                "data": base64.b64encode(data).decode("ascii"),
                "attributes": attributes,
                "messageId": "1",
            }
        }
        decoded = _decode(envelope)
        assert decoded is not None
        assert decoded["hospital_id"] == "h1"
        assert decoded["document_id"] == "d1"

    async def test_the_attributes_alone_are_enough(
        self, publisher: FakePublisher
    ) -> None:
        """A push with no body still names the document.

        The attributes duplicate the payload so a subscription filter can route
        on hospital without opening the message, and so a delivery that arrives
        without `data` is still actionable rather than dead-lettered.
        """
        from app.api.v1.worker import _decode

        await PubSubDispatcher(project_id="proj", topic="docs").dispatch(
            hospital_id="h1", intake_id="i1", document_id="d1"
        )
        _, _, attributes = publisher.published[0]

        decoded = _decode({"message": {"attributes": attributes}})
        assert decoded == attributes

    async def test_a_publish_failure_reaches_the_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not swallowed, unlike the inline path — and the difference is the point.

        Inline, the work is already scheduled and the image is stored. Here,
        nothing has been queued: swallowing would leave a document that is
        never read, never retried and never reported. The kiosk is better off
        being told the upload failed.
        """
        fake = FakePublisher(fail=RuntimeError("topic unreachable"))
        monkeypatch.setattr(
            "app.adapters.queue.dispatch._publisher_client", lambda: fake
        )
        dispatcher = PubSubDispatcher(project_id="proj", topic="docs")

        with pytest.raises(RuntimeError):
            await dispatcher.dispatch(
                hospital_id="h1", intake_id="i1", document_id="d1"
            )


class TestTheConfiguredChoice:
    def test_the_default_is_inline(self) -> None:
        """No broker required. This is the demo path when the wifi fails."""
        dispatcher = build_dispatcher(
            Settings(), background=FakeBackground(), service=FakeService()
        )
        assert dispatcher.name == "inline"

    def test_pubsub_is_selected_by_config(self, publisher: FakePublisher) -> None:
        settings = Settings(
            document_queue="pubsub", gcp_project="proj", pubsub_topic="docs"
        )
        dispatcher = build_dispatcher(
            settings, background=FakeBackground(), service=FakeService()
        )
        assert dispatcher.name == "pubsub"

    def test_pubsub_without_a_topic_refuses_to_build(self) -> None:
        """Fails at the first upload, loudly, rather than dropping documents.

        `DOCUMENT_QUEUE=pubsub` with no topic is a deployment that accepts
        photographs and queues none of them. There is no sensible fallback —
        quietly running inline would put OCR back in the API process that was
        deliberately split away from it.
        """
        settings = Settings(document_queue="pubsub", gcp_project="proj")
        with pytest.raises(RuntimeError, match="PUBSUB_TOPIC"):
            build_dispatcher(
                settings, background=FakeBackground(), service=FakeService()
            )

    def test_an_unknown_queue_is_rejected_at_startup(self) -> None:
        with pytest.raises(ValueError, match="document_queue"):
            Settings(document_queue="rabbitmq")
