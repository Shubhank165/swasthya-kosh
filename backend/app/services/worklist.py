"""The worklist and red-flag acknowledgement — §8.4.

Ordering is arrival time. A fired red-flag criterion raises an alert and pulls
the row into `pending_alerts`; it does **not** move the intake up the list.
Reordering a waiting room on a machine's reading of a symptom is a triage
decision, and this system does not make triage decisions — a person acknowledges
the alert and decides what happens next.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.clock import Clock
from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.domain.contradictions import detector
from app.domain.documents.alignment import align_medications
from app.domain.documents.ingredients import EMPTY_INDEX, IngredientIndex
from app.domain.record import IntakeStatus
from app.domain.worklist import Worklist, WorklistEntry, assemble, state_for
from app.events.bus import EventBus
from app.events.schemas import Event, EventName
from app.models.clinical import RedFlagEventRecord
from app.repositories.consent import AuditRepository
from app.repositories.intakes import IntakeRepository

logger = get_logger(__name__)

#: How far back a worklist looks by default. A dashboard showing last month's
#: OPD is a dashboard nobody reads.
DEFAULT_WINDOW = timedelta(hours=24)


class WorklistService:
    """Serves the dashboard's ordered list and records acknowledgements."""

    def __init__(
        self,
        *,
        intakes: IntakeRepository,
        audit: AuditRepository,
        bus: EventBus,
        clock: Clock,
        session: object = None,
        ingredients: IngredientIndex = EMPTY_INDEX,
    ) -> None:
        self._intakes = intakes
        self._audit = audit
        self._bus = bus
        self._clock = clock
        self._session = session
        #: Needed to derive the medication aliases before detection runs — a
        #: spoken "Metformin" and a printed "Metformin 900.2 mg BD" carry
        #: different field ids and do not compare without them.
        self._ingredients = ingredients

    async def worklist(
        self,
        *,
        hospital_id: str,
        department_code: str | None = None,
        window: timedelta = DEFAULT_WINDOW,
        limit: int = 200,
    ) -> Worklist:
        now = self._clock.now()
        rows = await self._intakes.for_department(
            hospital_id=hospital_id,
            department_code=department_code,
            since=now - window,
            limit=limit,
        )
        intake_ids = [row.id for row in rows]
        alerts = await self._intakes.unacknowledged_alert_counts(
            hospital_id=hospital_id, intake_ids=intake_ids
        )
        counts = await self._intakes.fact_counts(
            hospital_id=hospital_id, intake_ids=intake_ids
        )
        conflicts = await self._contradiction_counts(
            hospital_id=hospital_id, intake_ids=intake_ids
        )

        entries: list[WorklistEntry] = []
        for row in rows:
            fact_counts = counts.get(row.id, {})
            unacknowledged = alerts.get(row.id, 0)
            needs_verification = bool(fact_counts.get("needs_verification", 0))
            contradictions = conflicts.get(row.id, 0)
            needs_review = (
                row.repaired
                or row.needs_manual_review
                or needs_verification
                or contradictions > 0
            )
            entries.append(
                WorklistEntry(
                    intake_id=row.id,
                    hospital_id=row.hospital_id,
                    department_code=row.department_code,
                    state=state_for(
                        status=IntakeStatus(row.status),
                        unacknowledged_alerts=unacknowledged,
                        seen_at=row.seen_at,
                        needs_review=needs_review,
                    ),
                    intake_status=IntakeStatus(row.status),
                    arrived_at=row.received_at,
                    language=row.language,
                    unacknowledged_alerts=unacknowledged,
                    unresolved_count=int(fact_counts.get("unresolved", 0)),
                    contradiction_count=contradictions,
                    needs_verification=needs_verification,
                    repaired=row.repaired,
                    patient_ref_type=row.patient_ref_type,
                    seen_at=row.seen_at,
                )
            )
        return assemble(entries, department_code=department_code, generated_at=now)

    async def _contradiction_counts(
        self, *, hospital_id: str, intake_ids: list[str]
    ) -> dict[str, int]:
        """How many open conflicts each intake carries.

        Recomputed rather than stored, exactly as the record read does it, so a
        change to the detector or to the ingredient table applies to intakes
        already in the database. A stored count would be a second copy of a
        derived fact, and it would be the stale one.

        A count, never the conflicting values: this feeds a dashboard that may
        be visible from a waiting room.
        """
        facts = await self._intakes.facts_for(
            hospital_id=hospital_id, intake_ids=intake_ids
        )
        counted: dict[str, int] = {}
        for intake_id, live_facts in facts.items():
            aligned = (
                *live_facts,
                *align_medications(live_facts, self._ingredients),
            )
            counted[intake_id] = len(detector.detect(aligned))
        return counted

    async def acknowledge(
        self,
        *,
        hospital_id: str,
        intake_id: str,
        rule_id: str,
        actor_id: str,
        actor_role: str,
        note: str | None = None,
    ) -> dict[str, object]:
        """A human acknowledges a red-flag event.

        Acknowledgement is a record of a person having looked. It does not
        escalate anything, reorder anything or notify anything automatically —
        what the acknowledging clinician does next is their decision, made
        outside this system.

        Re-acknowledging is a conflict rather than a silent no-op: two people
        each believing the other has seen it is the failure mode worth being
        noisy about.
        """
        session = self._session
        assert session is not None
        result = await session.execute(  # type: ignore[attr-defined]
            select(RedFlagEventRecord).where(
                RedFlagEventRecord.hospital_id == hospital_id,
                RedFlagEventRecord.intake_id == intake_id,
                RedFlagEventRecord.rule_id == rule_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(
                f"no red-flag event {rule_id!r} on intake {intake_id}",
                details={"intake_id": intake_id, "rule_id": rule_id},
            )
        if row.acknowledged_by is not None:
            raise ConflictError(
                "this alert has already been acknowledged",
                details={
                    "acknowledged_by": row.acknowledged_by,
                    "acknowledged_at": row.acknowledged_at.isoformat()
                    if row.acknowledged_at
                    else None,
                },
            )

        now = self._clock.now()
        row.acknowledged_by = actor_id
        row.acknowledged_at = now
        row.acknowledgement_note = note

        await self._audit.write(
            hospital_id=hospital_id,
            occurred_at=now,
            actor_id=actor_id,
            actor_role=actor_role,
            action="redflag.acknowledged",
            entity_type="red_flag_event",
            entity_id=row.id,
            after={"rule_id": rule_id, "severity": row.severity},
            reason=note,
        )
        await self._bus.publish(
            Event(
                name=EventName.REDFLAG_ACKNOWLEDGED,
                occurred_at=now,
                intake_id=intake_id,
                alert_id=row.id,
                actor_id=actor_id,
                payload={"rule_id": rule_id, "severity": row.severity},
            )
        )
        logger.info(
            "redflag_acknowledged",
            intake_id=intake_id,
            rule_id=rule_id,
            actor_id=actor_id,
        )
        return {
            "intake_id": intake_id,
            "rule_id": rule_id,
            "acknowledged_by": actor_id,
            "acknowledged_at": now.isoformat(),
        }

    async def mark_seen(
        self, *, hospital_id: str, intake_id: str, actor_id: str, at: datetime | None = None
    ) -> None:
        when = at or self._clock.now()
        await self._intakes.mark_seen(
            hospital_id=hospital_id, intake_id=intake_id, actor_id=actor_id, at=when
        )
        await self._bus.publish(
            Event(
                name=EventName.INTAKE_SEEN,
                occurred_at=when,
                intake_id=intake_id,
                actor_id=actor_id,
            )
        )
