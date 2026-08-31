"""Application errors.

Each carries an HTTP status and a stable machine-readable `code`. Messages are
written for a developer or an integrator; none of them may contain clinical text,
because errors reach logs.
"""

from __future__ import annotations

from typing import Any


class MediKioskError(Exception):
    """Base class. `code` is stable across releases; `message` is not."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFoundError(MediKioskError):
    status_code = 404
    code = "not_found"


class ValidationError(MediKioskError):
    status_code = 422
    code = "validation_error"


class ConflictError(MediKioskError):
    status_code = 409
    code = "conflict"


class IdempotencyConflictError(ConflictError):
    """Same Idempotency-Key replayed with a different request body."""

    code = "idempotency_conflict"


class RevisionConflictError(ConflictError):
    """The client's `revision` is behind the stored one — a lost-update guard."""

    code = "revision_conflict"


class ForbiddenError(MediKioskError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(MediKioskError):
    status_code = 401
    code = "unauthorized"


class ContentError(MediKioskError):
    """Clinical content failed to load or validate. Fatal at startup by design:
    a pathway that does not parse must stop the build, not degrade silently."""

    status_code = 500
    code = "clinical_content_error"


class QueueError(MediKioskError):
    status_code = 409
    code = "queue_operation_rejected"


class ConsentError(MediKioskError):
    status_code = 403
    code = "consent_required"
