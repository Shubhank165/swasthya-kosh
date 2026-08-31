"""Facility seeding.

Creates a realistic AYUSH tertiary institute: the eight classical departments
plus weekday speciality clinics, and at least three concurrently open queues
exercising all three assignment policies — because a queue model that has only
ever been run against one policy has not been tested.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domain.clinical.provenance import QueueId, QueueInstanceId, UserId
from app.domain.queue.entities import (
    AssignmentPolicy,
    InstanceStatus,
    PriorityClass,
    QueueInstance,
    QueueMode,
    SessionName,
    UnservedPolicy,
)
from app.models.queue import DepartmentRecord, QueueInstanceRecord, QueueRecord
from app.repositories.queues import QueueRepository
from app.repositories.terminology import TerminologyRepository
from app.services.terminology import seed_terminology

logger = get_logger(__name__)

FACILITY = "All India Institute of Ayurveda, New Delhi"

#: The eight classical AYUSH OPD departments an institute of this size runs.
DEPARTMENTS: tuple[tuple[str, str], ...] = (
    ("KC", "Kayachikitsa"),
    ("PK", "Panchakarma"),
    ("ST", "Shalya Tantra"),
    ("SK", "Shalakya Tantra"),
    ("PT", "Prasuti Tantra & Stri Roga"),
    ("KB", "Kaumarbhritya"),
    ("SV", "Swasthavritta"),
    ("MR", "Manas Roga"),
)

#: (queue_id, name, dept, service_point, policy, prefix, session, weekdays,
#:  prefer_intake_ready, capacity)
#:
#: The three policies are all represented and all opened by `seed_facility`:
#: Kayachikitsa general is pooled across the department, Panchakarma is bound to
#: its therapy hall, and the Shalya consultant clinic belongs to one surgeon.
QueueSeed = tuple[
    str, str, str, str, AssignmentPolicy, str, SessionName, tuple[int, ...], bool, int | None
]

QUEUES: tuple[QueueSeed, ...] = (
    (
        "q-kc-general",
        "Kayachikitsa General OPD",
        "KC",
        "OPD-1",
        AssignmentPolicy.POOLED_BY_DEPARTMENT,
        "KC",
        SessionName.MORNING,
        (),
        True,
        120,
    ),
    (
        "q-pk-therapy",
        "Panchakarma Therapy OPD",
        "PK",
        "PK-HALL",
        AssignmentPolicy.PER_SERVICE_POINT,
        "PK",
        SessionName.MORNING,
        (),
        False,
        60,
    ),
    (
        "q-st-consultant",
        "Shalya Tantra Consultant Clinic",
        "ST",
        "OPD-4",
        AssignmentPolicy.PER_PRACTITIONER,
        "ST",
        SessionName.MORNING,
        (),
        False,
        40,
    ),
    (
        "q-sk-eye",
        "Shalakya Tantra Netra Clinic",
        "SK",
        "OPD-5",
        AssignmentPolicy.PER_SERVICE_POINT,
        "SK",
        SessionName.EVENING,
        (1, 3),  # Tuesday and Thursday speciality clinic
        False,
        30,
    ),
    (
        "q-pt-antenatal",
        "Prasuti Tantra Antenatal Clinic",
        "PT",
        "OPD-6",
        AssignmentPolicy.PER_PRACTITIONER,
        "PT",
        SessionName.MORNING,
        (0, 2, 4),
        False,
        35,
    ),
    (
        "q-kb-paediatric",
        "Kaumarbhritya OPD",
        "KB",
        "OPD-7",
        AssignmentPolicy.POOLED_BY_DEPARTMENT,
        "KB",
        SessionName.MORNING,
        (),
        True,
        50,
    ),
    (
        "q-sv-lifestyle",
        "Swasthavritta Lifestyle Clinic",
        "SV",
        "OPD-8",
        AssignmentPolicy.PER_SERVICE_POINT,
        "SV",
        SessionName.EVENING,
        (),
        False,
        40,
    ),
    (
        "q-mr-manas",
        "Manas Roga OPD",
        "MR",
        "OPD-9",
        AssignmentPolicy.PER_PRACTITIONER,
        "MR",
        SessionName.EVENING,
        (0, 2),
        False,
        25,
    ),
)

#: Queues opened by default, chosen so all three assignment policies run
#: concurrently on a seeded database.
DEFAULT_OPEN: tuple[tuple[str, str | None], ...] = (
    ("q-kc-general", "dr-kayachikitsa-1"),
    ("q-pk-therapy", None),
    ("q-st-consultant", "dr-shalya-1"),
    ("q-kb-paediatric", None),
)


async def seed_facility(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    clock: Clock | None = None,
    service_date: date | None = None,
) -> dict[str, int]:
    """Create departments, queues, today's instances and the terminology tables.

    Idempotent: running it twice leaves the same rows, so it is safe in an
    entrypoint script and safe to call from a test fixture.
    """
    settings = settings or get_settings()
    clock = clock or SystemClock()
    today = service_date or settings.today(clock)
    counts = {"departments": 0, "queues": 0, "instances": 0, "terminology": 0}

    for code, name in DEPARTMENTS:
        if await session.get(DepartmentRecord, code) is None:
            session.add(DepartmentRecord(code=code, name=name, facility=FACILITY))
            counts["departments"] += 1
    await session.flush()

    for (
        queue_id,
        name,
        dept,
        service_point,
        policy,
        prefix,
        session_name,
        weekdays,
        prefer_ready,
        capacity,
    ) in QUEUES:
        if await session.get(QueueRecord, queue_id) is not None:
            continue
        session.add(
            QueueRecord(
                id=queue_id,
                name=name,
                department_code=dept,
                service_point=service_point,
                assignment_policy=policy.value,
                token_prefix=prefix,
                capacity=capacity,
                schedule_days=list(weekdays),
                session=session_name.value,
                priority_classes=[p.value for p in PriorityClass],
                # Off unless the facility opted in, per the brief's default.
                prefer_intake_ready=prefer_ready and settings.prefer_intake_ready,
                intake_ready_window=settings.intake_ready_window,
                max_overtaken=settings.max_overtaken,
                recall_after_tokens=settings.recall_after_tokens,
                max_recalls=settings.max_recalls,
                unserved_policy=UnservedPolicy.CARRY_FORWARD.value,
                mode=(
                    QueueMode.SHADOW.value
                    if settings.is_shadow_mode
                    else QueueMode.SOURCE_OF_TRUTH.value
                ),
            )
        )
        counts["queues"] += 1
    await session.flush()

    repository = QueueRepository(session)
    for queue_id, practitioner in DEFAULT_OPEN:
        queue = await repository.get_queue(queue_id)
        if queue is None:
            continue
        existing = await session.execute(
            select(QueueInstanceRecord).where(
                QueueInstanceRecord.queue_id == queue_id,
                QueueInstanceRecord.service_date == today,
                QueueInstanceRecord.session == queue.session.value,
            )
        )
        if existing.scalars().first() is not None:
            continue
        await repository.create_instance(
            QueueInstance(
                instance_id=QueueInstanceId(f"qi-{queue_id}-{today.isoformat()}"),
                queue_id=QueueId(queue_id),
                service_date=today,
                session=queue.session,
                status=InstanceStatus.OPEN,
                practitioner_id=UserId(practitioner) if practitioner else None,
                service_point=queue.service_point,
                opened_at=_start_of_day(clock.now()),
            )
        )
        counts["instances"] += 1

    counts["terminology"] = await seed_terminology(
        TerminologyRepository(session), settings.terminology_dir
    )
    await session.flush()
    logger.info(
        "facility_seeded",
        count=counts["queues"],
        state="seeded",
    )
    return counts


def _start_of_day(now: datetime) -> datetime:
    return now.replace(hour=8, minute=0, second=0, microsecond=0)
