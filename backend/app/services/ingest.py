"""Ingest — §5.

```
POST /api/v1/intakes/ingest
Idempotency-Key: <uuid>
Body: the kiosk JSON, any registered schema_version
```

1. Authenticate the kiosk — scoped to one `hospital_id`.
2. Detect the version, dispatch to the normalizer.
3. Validate. A failure goes to repair, not to a rejection.
4. Build the canonical record, persist, emit `intake.received`.
5. Return `{intake_id, status, unresolved_fields, needs_review}`.

Two things this service does not do, and the reason each matters:

**It does not run the interview.** No state machine, no question selection, no
turn logic. Those live on the Jetson. A second implementation of question order
would eventually disagree with the first, and the patient is standing in front
of the first one.

**It does not re-evaluate red flags.** A `red_flags` entry in the payload is an
*event that already fired* — the device stopped the interview over it. The
backend persists it, emits it and surfaces it for acknowledgement. If the
backend re-ran the rules and disagreed, there would be no principled way to
choose, and the disagreement itself would be invisible.

**Partial intakes are first-class.** `status: "partial"` persists normally and
the doctor sees what exists with the rest marked unanswered. An incomplete
intake is never rejected: the patient still answered the questions they
answered.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.adapters.protocols import RepairProvider
from app.core.clock import Clock
from app.core.errors import ConfigurationError
from app.core.ids import IdFactory
from app.core.logging import get_logger
from app.domain.contradictions import detector
from app.domain.record import CanonicalRecord, Fact
from app.events.bus import EventBus
from app.events.schemas import Event, EventName
from app.normalize.from_kiosk_v0_1 import payload_fingerprint
from app.normalize.registry import UnsupportedSchemaVersion, normalize
from app.repositories.consent import AuditRepository, IngestRawRepository
from app.repositories.intakes import IntakeRepository
from app.services import repair as repair_path

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestResult:
    """What the kiosk gets back.

    `unresolved_fields` is the useful half: it is the list the device can show a
    member of staff so a human can fill the gaps before the consultation, which
    is a better outcome than the doctor discovering them.
    """

    #: Where the intake lives, and `None` when it does not live anywhere.
    #:
    #: An unusable payload is kept in `ingest_raw` for a human to recover, and
    #: `ingest_raw` is not an intake: nothing addressed by intake id — the
    #: report, a document upload, the worklist — can find it. This field used
    #: to carry the payload fingerprint in that case, which looked exactly like
    #: an identifier and 404'd on every route that took one, so a device would
    #: photograph a prescription, post it, and be told the intake did not
    #: exist. Saying `None` is the same fact without the wild goose chase.
    intake_id: str | None
    status: str
    unresolved_fields: tuple[str, ...]
    needs_review: bool
    repaired: bool = False
    needs_manual_review: bool = False
    red_flags: tuple[str, ...] = ()
    contradictions: int = 0
    demo: bool = False
    #: Why the payload could not be used, and what failed its contract. Empty
    #: on the happy path. Structural only — `safe_errors` strips the offending
    #: values, because those are the patient's own words and they belong in
    #: `ingest_raw`, which is access-controlled, not in an API response.
    reason: str | None = None
    errors: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "intake_id": self.intake_id,
            "status": self.status,
            "unresolved_fields": list(self.unresolved_fields),
            "needs_review": self.needs_review,
            "repaired": self.repaired,
            "needs_manual_review": self.needs_manual_review,
            "red_flags": list(self.red_flags),
            "contradictions": self.contradictions,
            "demo": self.demo,
            "reason": self.reason,
            "errors": [dict(e) for e in self.errors],
        }


class IngestService:
    """Receives finished intakes."""

    def __init__(
        self,
        *,
        intakes: IntakeRepository,
        raw: IngestRawRepository,
        audit: AuditRepository,
        bus: EventBus,
        clock: Clock,
        ids: IdFactory,
        repair_provider: RepairProvider | None = None,
        repair_max_attempts: int = 1,
        demo: bool = False,
    ) -> None:
        self._intakes = intakes
        self._raw = raw
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._ids = ids
        self._repair = repair_provider
        self._repair_max_attempts = repair_max_attempts
        self._demo = demo

    async def ingest(
        self, payload: Mapping[str, Any], *, hospital_id: str, actor_id: str
    ) -> IngestResult:
        """Take one kiosk payload all the way to a persisted record."""
        now = self._clock.now()

        # The kiosk's token is scoped to one hospital, and that scope wins over
        # anything the body claims. A device that says it belongs somewhere else
        # is either misconfigured or lying, and neither is a reason to write a
        # row into another hospital's data.
        body = dict(payload)
        claimed = body.get("hospital_id")
        if claimed and claimed != hospital_id:
            logger.warning(
                "ingest_hospital_mismatch",
                error_code="hospital_mismatch",
                intake_id=str(body.get("intake_id")),
            )
        body["hospital_id"] = hospital_id

        outcome = await repair_path.attempt(
            body, provider=self._repair, max_attempts=self._repair_max_attempts
        )

        if outcome.payload is None:
            return await self._store_unusable(
                body, outcome=outcome, hospital_id=hospital_id, now=now, actor_id=actor_id
            )

        try:
            record = normalize(outcome.payload, now=now)
        except UnsupportedSchemaVersion:
            return await self._store_unusable(
                body,
                outcome=repair_path.RepairOutcome(
                    payload=None,
                    errors=outcome.errors,
                    reason="unsupported_version",
                ),
                hospital_id=hospital_id,
                now=now,
                actor_id=actor_id,
            )

        if outcome.repaired:
            record = _stamp_repaired(record, touched=outcome.touched_fields)

        # A submission for an intake we already hold is a retry, not a second
        # patient. `Idempotency-Key` is the first line of defence and the one
        # the device is asked to send; this is the second, and it needs no
        # header at all, because the kiosk's `intake_id` already identifies the
        # interview uniquely. Without it a retry sent without the header hits a
        # primary key violation and the kiosk sees a 500 for a request that
        # succeeded.
        #
        # Nothing is written. The stored answers stay as they are — a replay
        # must never clobber a value staff have corrected since.
        if await self._intakes.exists(
            hospital_id=hospital_id, intake_id=str(record.intake_id)
        ):
            return await self._replay(
                hospital_id=hospital_id,
                intake_id=str(record.intake_id),
                now=now,
                actor_id=actor_id,
            )

        # Contradictions are computed at ingest against whatever is on the
        # record now — which at this point is the voice channel alone. They are
        # recomputed on every read, so a document arriving later surfaces its
        # conflicts without anything being re-ingested.
        record = record.model_copy(
            update={"contradictions": list(detector.detect(record.live_facts()))}
        )

        try:
            await self._intakes.create(record, received_at=now)
        except IntegrityError as exc:
            # The only foreign key an intake has is its hospital, and the only
            # way it is unsatisfied is a kiosk token naming a hospital that was
            # never seeded — a deployment where the token map was written before
            # the seeder ran, or against the wrong database. Until this build it
            # surfaced as a bare `Internal Server Error`, so a five-minute
            # configuration mistake read as a broken backend.
            if "hospital" not in str(exc.orig):
                raise
            raise ConfigurationError(
                f"hospital {hospital_id!r} does not exist; the kiosk token is "
                "scoped to a hospital this database has never been seeded with",
                details={"hospital_id": hospital_id},
            ) from exc
        await self._audit.write(
            hospital_id=hospital_id,
            occurred_at=now,
            actor_id=actor_id,
            actor_role="kiosk",
            action="intake.ingested",
            entity_type="intake",
            entity_id=str(record.intake_id),
            after={
                "status": record.status.value,
                "fact_count": len(record.facts),
                "red_flag_count": len(record.red_flags),
                "repaired": record.provenance.repaired,
                "schema_version": record.provenance.schema_version,
            },
        )

        await self._emit(record, now=now)

        logger.info(
            "intake_ingested",
            intake_id=str(record.intake_id),
            status=record.status.value,
            count=len(record.facts),
            repaired=record.provenance.repaired,
        )

        return IngestResult(
            intake_id=str(record.intake_id),
            status=record.status.value,
            unresolved_fields=record.unresolved_fields(),
            needs_review=record.needs_review,
            repaired=record.provenance.repaired,
            red_flags=tuple(sorted(e.rule_id for e in record.red_flags)),
            contradictions=len(record.contradictions),
            demo=self._demo,
        )

    async def _replay(
        self, *, hospital_id: str, intake_id: str, now: datetime, actor_id: str
    ) -> IngestResult:
        """The result for an intake that is already stored.

        Read back rather than recomputed from the payload, so what the kiosk is
        told matches what the doctor will see — including any correction a
        member of staff has made since the first submission.

        Audited: a duplicate arriving hours later is a device with a stuck
        outbox, and that is worth being able to find.
        """
        stored = await self._intakes.load(hospital_id=hospital_id, intake_id=intake_id)
        await self._audit.write(
            hospital_id=hospital_id,
            occurred_at=now,
            actor_id=actor_id,
            actor_role="kiosk",
            action="intake.duplicate_submission",
            entity_type="intake",
            entity_id=intake_id,
            after={"status": stored.status.value},
        )
        logger.info("intake_duplicate_submission", intake_id=intake_id)
        return IngestResult(
            intake_id=intake_id,
            status=stored.status.value,
            unresolved_fields=stored.unresolved_fields(),
            needs_review=stored.needs_review,
            repaired=stored.provenance.repaired,
            red_flags=tuple(sorted(e.rule_id for e in stored.red_flags)),
            contradictions=len(detector.detect(stored.live_facts())),
            demo=self._demo,
        )

    async def _emit(self, record: CanonicalRecord, *, now: datetime) -> None:
        """Publish what happened. Identifiers and counters only."""
        events = [
            Event(
                name=EventName.INTAKE_RECEIVED,
                occurred_at=now,
                intake_id=str(record.intake_id),
                department_code=record.department_code,
                payload={
                    "status": record.status.value,
                    "unresolved_count": len(record.unresolved_fields()),
                    "needs_review": record.needs_review,
                },
            )
        ]
        events.extend(
            Event(
                name=EventName.REDFLAG_RECEIVED,
                occurred_at=now,
                intake_id=str(record.intake_id),
                department_code=record.department_code,
                payload={"rule_id": event.rule_id, "severity": event.severity},
            )
            for event in record.red_flags
        )
        await self._bus.publish_all(events)

    async def _store_unusable(
        self,
        payload: Mapping[str, Any],
        *,
        outcome: repair_path.RepairOutcome,
        hospital_id: str,
        now: datetime,
        actor_id: str,
    ) -> IngestResult:
        """Keep a payload we could not normalise, and say so plainly.

        The kiosk gets a 200 with `needs_manual_review: true` rather than a 4xx.
        That is deliberate: a retry would produce the same failure, and a device
        that keeps retrying a payload nobody can parse is a device that
        eventually drops it. Accepted-and-flagged is the outcome that keeps the
        intake recoverable.
        """
        fingerprint = payload_fingerprint(payload)
        claimed_intake_id = payload.get("intake_id")

        existing = await self._raw.by_fingerprint(
            hospital_id=hospital_id, fingerprint=fingerprint
        )
        if existing is None:
            await self._raw.store(
                record_id=self._ids.new_id("raw"),
                hospital_id=hospital_id,
                claimed_intake_id=str(claimed_intake_id) if claimed_intake_id else None,
                schema_version=(
                    str(payload.get("schema_version"))
                    if payload.get("schema_version")
                    else None
                ),
                reason=outcome.reason,
                error_detail={"errors": [dict(e) for e in outcome.errors]},
                payload=dict(payload),
                payload_fingerprint=fingerprint,
                # A repair that ran and was thrown out still ran. The two
                # reasons that are *not* an attempt are "repair_disabled" and
                # "unsupported_version", where the provider was never called.
                repair_attempted=self._repair is not None
                and outcome.reason
                in ("repair_failed", "repair_changed_identity"),
                received_at=now,
            )

        await self._audit.write(
            hospital_id=hospital_id,
            occurred_at=now,
            actor_id=actor_id,
            actor_role="kiosk",
            action="intake.unusable",
            entity_type="ingest_raw",
            entity_id=fingerprint,
            after={"reason": outcome.reason, "error_count": len(outcome.errors)},
        )

        logger.warning(
            "intake_needs_manual_review",
            error_code=outcome.reason,
            count=len(outcome.errors),
        )

        return IngestResult(
            # Not the claimed id and not the fingerprint. Neither addresses an
            # intake, because this payload did not become one — it became an
            # `ingest_raw` row for a human to recover. A device that is handed
            # something id-shaped here will use it, and every route that takes
            # an intake id will tell it the intake does not exist.
            intake_id=None,
            status="needs_manual_review",
            unresolved_fields=(),
            needs_review=True,
            repaired=False,
            needs_manual_review=True,
            demo=self._demo,
            # What was wrong, so the device can be fixed. Without this the only
            # signal is `needs_manual_review` with nothing unresolved, which
            # reads as "the record was fine and we filed it for review anyway".
            reason=outcome.reason,
            errors=outcome.errors,
        )


def _stamp_repaired(record: CanonicalRecord, *, touched: frozenset[str]) -> CanonicalRecord:
    """Mark the facts the repair produced.

    Only the fields repair actually changed. A payload that failed on one
    malformed entry should not demote the nineteen that arrived clean —
    over-marking makes the marker meaningless, and a meaningless marker is one a
    physician stops reading.
    """
    marked: list[Fact] = [
        f.model_copy(update={"repaired": True, "physician_verified": False})
        if (not touched or f.field_id in touched)
        else f
        for f in record.facts
    ]
    return record.model_copy(
        update={
            "facts": marked,
            "provenance": record.provenance.model_copy(update={"repaired": True}),
        }
    )
