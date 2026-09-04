"""The OCR worker's entry point — §6, §11.

Reading a document is asynchronous. Nothing about the patient's experience waits
on it: they have already answered the questions and gone to sit down, and the
doctor sees the document section fill in when it fills in.

Two ways that work is dispatched, and **both call the same
`DocumentService.process`**, so they cannot drift:

- **Locally**, a FastAPI background task in the upload handler. That is what
  makes `docker compose up` a complete pipeline with no broker — which matters,
  because it is the demo path when venue wifi fails.
- **On Cloud Run**, a Pub/Sub push subscription to this router, deployed as a
  separate service from the same image. Separate because OCR is bursty and the
  API is not: the worker scales to zero between patients and the API does not
  have to hold a request open while a model reads a photograph.

This router is registered only when `PUBSUB_PUSH_ENABLED` is set. The public API
service leaves it off, so the route does not exist there at all rather than
existing and being guarded — an endpoint that is absent cannot be probed.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Annotated, Any

from fastapi import APIRouter, Header, Response, status

from app.api.deps import SettingsDep, WorkerDocumentServiceDep
from app.core.errors import MediKioskError
from app.core.logging import get_logger
from app.db.tenancy import tenant_scope

logger = get_logger(__name__)

router = APIRouter(prefix="/worker", tags=["worker"])


@router.post(
    "/documents",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Pub/Sub push: read one uploaded document",
    include_in_schema=False,
)
async def process_document(
    settings: SettingsDep,
    service: WorkerDocumentServiceDep,
    body: dict[str, Any],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Run OCR for one document, dispatched by Pub/Sub.

    **The status code is the retry policy**, so it is chosen rather than
    defaulted:

    - `204` — done, or permanently undoable. Pub/Sub acknowledges and stops. A
      malformed envelope and an unknown document id both land here: redelivering
      either produces the same failure for as long as the retention window
      allows, and a poison message that never acks is a subscription that never
      drains.
    - `500` — transient. Pub/Sub retries with backoff. A provider outage or a
      database blip belongs here, because the work genuinely can succeed later.

    Getting this backwards in either direction is expensive: a permanent failure
    marked retryable pins a worker to one bad message, and a transient failure
    acknowledged drops a patient's prescription silently.
    """
    if settings.pubsub_push_token:
        # Defence in depth. Cloud Run's IAM check is the primary control — the
        # worker service is deployed `--no-allow-unauthenticated` and only the
        # subscription's service account may invoke it.
        expected = f"Bearer {settings.pubsub_push_token}"
        if authorization != expected:
            logger.warning("pubsub_push_rejected")
            return Response(status_code=status.HTTP_403_FORBIDDEN)

    payload = _decode(body)
    if payload is None:
        # Acknowledged deliberately: see the docstring. Logged at warning so a
        # publisher emitting rubbish is visible rather than silently dropped.
        logger.warning("pubsub_push_undecodable")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    hospital_id = str(payload.get("hospital_id") or "")
    document_id = str(payload.get("document_id") or "")
    if not hospital_id or not document_id:
        logger.warning("pubsub_push_incomplete", document_id=document_id or None)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        # The tenant context is set from the message rather than from a
        # principal — there is no user here — so the guard in `db/tenancy.py`
        # has something to check every query against, exactly as in a request.
        with tenant_scope(hospital_id):
            await service.process(hospital_id=hospital_id, document_id=document_id)
    except MediKioskError as exc:
        if exc.status_code < 500:
            # The document does not exist, or is in a state processing cannot
            # act on. Redelivery cannot change that.
            logger.warning(
                "pubsub_push_permanent_failure",
                document_id=document_id,
                error_code=exc.code,
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _decode(body: dict[str, Any]) -> dict[str, Any] | None:
    """The event out of a Pub/Sub push envelope.

    Accepts the envelope Pub/Sub actually sends — `{"message": {"data": ...}}`,
    base64 in `data` — and a bare event object, which is what a `curl` during an
    incident sends and what the tests send. Anything else is `None`.
    """
    message = body.get("message")
    if not isinstance(message, dict):
        return body if "document_id" in body else None

    attributes = message.get("attributes")
    data = message.get("data")
    if not isinstance(data, str):
        return attributes if isinstance(attributes, dict) else None

    try:
        decoded = json.loads(base64.b64decode(data).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(decoded, dict):
        return None
    # Attributes win: a publisher that set them meant them, and they survive a
    # payload shape change.
    if isinstance(attributes, dict):
        return {**decoded, **attributes}
    return decoded
