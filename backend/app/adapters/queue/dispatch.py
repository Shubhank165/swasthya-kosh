"""Where a newly uploaded document's OCR work goes — §6, §11.

Two shapes, one call site.

- **inline** — a FastAPI background task in the API process. This is what makes
  `docker compose up` a complete pipeline with no broker, which matters because
  it is the demo path when the venue wifi fails.
- **pubsub** — a message on a topic, delivered by push to a second Cloud Run
  service running the same image. OCR is bursty and the API is not: the worker
  scales to zero between patients, and the API never holds a request open while
  a model reads a photograph.

Both end at the same `DocumentService.process`, so the two paths cannot drift
into producing different records from the same photograph.

The message carries **identifiers only** — hospital, intake, document. No image,
no extracted text, no patient detail. A Pub/Sub message is retained for days,
is visible to anyone with subscriber rights, and lands in a dead-letter topic
when it fails; none of those are places a prescription belongs. The worker
re-reads the document from the database and the object store under the tenant
scope named in the message.
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Any, Protocol

from app.core.logging import get_logger

logger = get_logger(__name__)


class DocumentDispatcher(Protocol):
    """Hands one document to whatever will read it."""

    name: str

    async def dispatch(
        self, *, hospital_id: str, intake_id: str, document_id: str
    ) -> None: ...


class InlineDispatcher:
    """Runs OCR in this process, after the response has gone out.

    Bound per request, because `BackgroundTasks` and the request-scoped
    `DocumentService` both belong to one request.
    """

    name = "inline"

    def __init__(self, background: Any, service: Any) -> None:
        self._background = background
        self._service = service

    async def dispatch(
        self, *, hospital_id: str, intake_id: str, document_id: str
    ) -> None:
        self._background.add_task(
            _process_quietly, self._service, hospital_id, document_id
        )


async def _process_quietly(service: Any, hospital_id: str, document_id: str) -> None:
    """Run OCR without letting a failure surface as a request error.

    The upload already succeeded and the image is stored. A provider outage
    leaves the document `failed` on the record and the report says "not yet
    processed", which is the honest state — rather than the kiosk concluding the
    upload did not happen and sending the photograph again.
    """
    try:
        await service.process(hospital_id=hospital_id, document_id=document_id)
    except Exception:
        logger.warning("document_processing_failed", document_id=document_id)


class PubSubDispatcher:
    """Publishes the job and returns.

    The publish is a blocking gRPC call in a thread, awaited: if the topic is
    unreachable the upload handler is told, rather than the message being
    dropped into a future nobody checks. A document that was accepted but never
    queued is a document the physician is never shown and never told about.
    """

    name = "pubsub"

    def __init__(self, *, project_id: str, topic: str) -> None:
        self._publisher = _publisher_client()
        self._topic_path = self._publisher.topic_path(project_id, topic)

    async def dispatch(
        self, *, hospital_id: str, intake_id: str, document_id: str
    ) -> None:
        payload = {
            "hospital_id": hospital_id,
            "intake_id": intake_id,
            "document_id": document_id,
        }
        data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

        def _publish() -> str:
            future = self._publisher.publish(
                self._topic_path,
                data,
                # Duplicated as attributes so the push endpoint can read them
                # without base64-decoding, and so a subscription filter could
                # route one hospital's traffic without opening the body.
                hospital_id=hospital_id,
                intake_id=intake_id,
                document_id=document_id,
            )
            return str(future.result(timeout=30))

        message_id = await asyncio.to_thread(_publish)
        logger.info(
            "document_queued", document_id=document_id, message_id=message_id
        )


@lru_cache(maxsize=1)
def _publisher_client() -> Any:
    """One publisher per process.

    The client holds a gRPC channel and a batching thread. Building one per
    upload would open a connection per photograph and batch nothing.
    """
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


def build_dispatcher(
    settings: Any, *, background: Any, service: Any
) -> DocumentDispatcher:
    """The configured dispatcher for one request."""
    if settings.document_queue == "pubsub":
        if not settings.gcp_project or not settings.pubsub_topic:
            raise RuntimeError(
                "DOCUMENT_QUEUE=pubsub needs GCP_PROJECT and PUBSUB_TOPIC set"
            )
        return PubSubDispatcher(
            project_id=settings.gcp_project, topic=settings.pubsub_topic
        )
    return InlineDispatcher(background, service)
