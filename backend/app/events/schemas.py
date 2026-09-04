"""Event payloads.

Every event carries identifiers, enums and counters — never clinical text. That
is not an accident of design: these payloads fan out to a waiting-room display
and into logs, and both are places a patient's history must never appear. The
PHI filter in `core/logging.py` is the backstop; this is the first line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class EventName(StrEnum):
    """The complete published event vocabulary.

    Note the tense. `intake.received` and `intake.redflag.received` — not
    `started`, not `raised`. The backend does not start intakes and does not
    raise red flags; the Jetson does both, and these events record their
    arrival. The name is the clearest place to say which side owns the decision.
    """

    INTAKE_RECEIVED = "intake.received"
    INTAKE_UPDATED = "intake.updated"
    INTAKE_NEEDS_REVIEW = "intake.needs_review"
    INTAKE_SEEN = "intake.seen"

    #: A criterion that fired on the device, arriving here.
    REDFLAG_RECEIVED = "intake.redflag.received"
    REDFLAG_ACKNOWLEDGED = "intake.redflag.acknowledged"

    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_PROCESSED = "document.processed"
    DOCUMENT_LOW_CONFIDENCE = "document.low_confidence"
    DOCUMENT_REJECTED = "document.rejected"

    CONTRADICTION_DETECTED = "intake.contradiction.detected"

    REPORT_READY = "report.ready"
    REPORT_PHYSICIAN_VERIFIED = "report.physician_verified"

    CONSENT_RECORDED = "consent.recorded"


#: Payload keys that may never appear on an event. Enforced by `Event.__post_init__`
#: and by a safety test, so a well-meaning addition cannot leak PHI to a display.
FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "text",
        "answer",
        "utterance",
        "transcript",
        "original_expression",
        "summary",
        "report",
        "patient_name",
        "name",
        "phone",
        "address",
        "abha_id",
        "diagnosis",
        "medications",
        "value",
        "question",
        "prompt",
    }
)


class PayloadError(ValueError):
    """An event payload carried a forbidden key."""


@dataclass(frozen=True, slots=True)
class Event:
    """One published event."""

    name: EventName
    occurred_at: datetime
    #: Fan-out key: the dashboard subscribes by department.
    department_code: str | None = None
    intake_id: str | None = None
    report_id: str | None = None
    alert_id: str | None = None
    document_id: str | None = None
    actor_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        forbidden = sorted(set(self.payload) & FORBIDDEN_PAYLOAD_KEYS)
        if forbidden:
            raise PayloadError(
                f"event {self.name} carries forbidden payload keys {forbidden}; "
                "events must never contain clinical text"
            )

    def to_dict(self) -> dict[str, Any]:
        """Wire form. Used by the WebSocket hub and the event log."""
        body: dict[str, Any] = {
            "event": self.name.value,
            "occurred_at": self.occurred_at.isoformat(),
        }
        for key, value in (
            ("department_code", self.department_code),
            ("intake_id", self.intake_id),
            ("report_id", self.report_id),
            ("alert_id", self.alert_id),
            ("document_id", self.document_id),
            ("actor_id", self.actor_id),
        ):
            if value is not None:
                body[key] = value
        if self.payload:
            body["payload"] = dict(self.payload)
        return body
