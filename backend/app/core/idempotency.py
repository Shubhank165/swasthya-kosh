"""Idempotency for mutating endpoints.

A kiosk on a hospital LAN loses the network mid-submission more often than
anyone would like. When it retries, the retry must be a no-op that returns the
original response — not a duplicate fact, and not a clobber of an answer the
patient has since corrected.

Two mechanisms, both needed:
  - `Idempotency-Key`: the same key replays the stored response.
  - intake `revision`: a monotonic counter, so a stale client cannot overwrite a
    newer state even with a fresh key.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.core.errors import IdempotencyConflictError, RevisionConflictError


def fingerprint(payload: Any) -> str:
    """Stable hash of a request body. Key order must not change the result."""
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """A completed request, keyed by its `Idempotency-Key`."""

    key: str
    endpoint: str
    request_fingerprint: str
    response_body: dict[str, Any]
    status_code: int
    created_at: datetime


class IdempotencyStore(Protocol):
    async def get(self, key: str, endpoint: str) -> IdempotencyRecord | None: ...

    async def put(self, record: IdempotencyRecord) -> None: ...


class InMemoryIdempotencyStore:
    """Process-local store. Used by tests and single-node deployments; the
    Postgres-backed store in `repositories/` is what production runs."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], IdempotencyRecord] = {}

    async def get(self, key: str, endpoint: str) -> IdempotencyRecord | None:
        return self._records.get((key, endpoint))

    async def put(self, record: IdempotencyRecord) -> None:
        self._records[(record.key, record.endpoint)] = record


def check_replay(
    record: IdempotencyRecord | None, *, payload: Any
) -> IdempotencyRecord | None:
    """Return the stored response for a genuine replay, or None for a new request.

    A key reused with a *different* body is a client bug, not a retry, and is
    rejected rather than served the wrong stored response.
    """
    if record is None:
        return None
    if record.request_fingerprint != fingerprint(payload):
        raise IdempotencyConflictError(
            "Idempotency-Key was reused with a different request body",
            details={"key": record.key, "endpoint": record.endpoint},
        )
    return record


def check_revision(*, expected: int | None, actual: int) -> None:
    """Guard against a stale client overwriting newer state.

    `expected is None` means the client did not claim a revision, which is
    allowed for the first write of a session and for read-modify-write flows
    that hold no prior state.
    """
    if expected is None:
        return
    if expected < actual:
        raise RevisionConflictError(
            "the submitted revision is behind the stored intake revision",
            details={"submitted_revision": expected, "current_revision": actual},
        )
    if expected > actual:
        raise RevisionConflictError(
            "the submitted revision is ahead of the stored intake revision",
            details={"submitted_revision": expected, "current_revision": actual},
        )
