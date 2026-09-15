"""Seed data for local development and the demo.

A seeded hospital with departments and a handful of intakes — §13.2 — so
`make dev` gives something to look at rather than an empty worklist, and so the
demo has a story that does not depend on somebody remembering to run the kiosk
first.

Deterministic. Ids are fixed, timestamps are relative to a fixed base, and
running the seeder twice is a no-op. A demo that looks different every run is a
demo nobody can rehearse.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.ids import SequentialIdFactory
from app.core.logging import get_logger
from app.db.tenancy import tenant_scope
from app.events.bus import InProcessBus
from app.normalize.from_kiosk_v0_1 import intake_uuid
from app.repositories.consent import AuditRepository, IngestRawRepository
from app.repositories.intakes import IntakeRepository
from app.repositories.patients import (
    HospitalRepository,
    PatientLinkRepository,
    PatientRepository,
)
from app.repositories.terminology import TerminologyRepository
from app.services.ingest import IngestService
from app.services.patient_auth import phone_ref
from app.services.terminology import seed_terminology

logger = get_logger(__name__)

HOSPITAL_ID = "aiia-delhi"
#: A realistic AYUSH OPD rather than a sample of one. Four departments left a
#: woman needing gynaecology and a parent with a sick child no destination but
#: the escape hatch — which is a routing failure, not a cosmetic one. Display
#: names for all eight already existed in `api/v1/hospitals.py`; only the seed
#: was short.
DEPARTMENTS: list[str] = [
    "kayachikitsa",
    "panchakarma",
    "shalya",
    "shalakya",
    "prasuti",
    "kaumarbhritya",
    "swasthavritta",
    "general",
]

#: The demo patient. Sign in to the app with this number and the visits below
#: are already there. An invented number in the reserved-for-fiction range, and
#: an ABHA address from `adapters/abha/fixtures/mock_directory.json`.
DEMO_PHONE = "9876543210"
DEMO_ABHA = "asha.devi@sbx"
SECOND_ABHA = "ramesh.kumar@sbx"

#: Fixed, so a seeded demo reads the same on every machine.
_BASE = datetime(2026, 9, 3, 9, 0, 0, tzinfo=UTC)


def _turn(turn_id: int, question_id: str, transcript: str, confidence: float) -> dict[str, Any]:
    return {
        "turn_id": turn_id,
        "question_id": question_id,
        "transcript": transcript,
        "asr_confidence": confidence,
    }


def sample_payloads() -> list[dict[str, Any]]:
    """Four intakes covering the states the dashboard has to render.

    One complete, one partial, one that fired a red flag, and one in English.
    They are the demo, and each of the four is on screen for a reason: the
    partial one shows unresolved fields worded as "not established", and the
    red-flag one shows an alert waiting for a human to acknowledge it.
    """
    return [
        {
            "schema_version": "0.1",
            "intake_id": "3f1c2a10-0000-4000-8000-000000000001",
            "kiosk_id": "kiosk-aiia-01",
            "hospital_id": HOSPITAL_ID,
            "started_at": (_BASE + timedelta(minutes=2)).isoformat(),
            "completed_at": (_BASE + timedelta(minutes=9)).isoformat(),
            "status": "complete",
            "language": "hi",
            "reporter": "self",
            "department_code": "kayachikitsa",
            "patient_ref": {"type": "hospital_id", "value": "UHID-100241"},
            "turns": [
                _turn(1, "ask_complaint", "पेट में दर्द", 0.93),
                _turn(3, "ask_duration", "तीन दिन से", 0.91),
                _turn(5, "ask_severity", "छह", 0.88),
                _turn(7, "ask_medications", "मेटफॉर्मिन लेता हूँ", 0.84),
            ],
            "fields": {
                "chief_complaint": {
                    "value": "abdominal_pain",
                    "status": "answered",
                    "original_text": "पेट में दर्द",
                    "source_turn": 1,
                },
                "duration": {
                    "value": {"n": 3, "unit": "day"},
                    "status": "answered",
                    "source_turn": 3,
                },
                "severity": {"value": 6, "status": "answered", "source_turn": 5},
                "known_diabetes": {"value": True, "status": "answered", "source_turn": 7},
                "current_medications": {
                    "value": "Metformin 500",
                    "status": "answered",
                    "original_text": "मेटफॉर्मिन लेता हूँ",
                    "source_turn": 7,
                },
                "drug_allergy": {"value": False, "status": "answered", "source_turn": 8},
                "breathlessness": {"value": None, "status": "not_asked"},
            },
            "red_flags": [],
            "engine_version": "jetson-0.4.1",
            "content_version": "questions-2026-09-01",
        },
        {
            "schema_version": "0.1",
            "intake_id": "3f1c2a10-0000-4000-8000-000000000002",
            "kiosk_id": "kiosk-aiia-01",
            "hospital_id": HOSPITAL_ID,
            "started_at": (_BASE + timedelta(minutes=20)).isoformat(),
            "completed_at": (_BASE + timedelta(minutes=24)).isoformat(),
            # The patient was called before the interview finished. Everything
            # they did answer is kept.
            "status": "partial",
            "language": "hi",
            "reporter": "family_attendant",
            "department_code": "kayachikitsa",
            "patient_ref": {"type": "guest"},
            "turns": [
                _turn(1, "ask_complaint", "बुखार", 0.90),
                _turn(3, "ask_duration", "शायद दो हफ्ते", 0.72),
            ],
            "fields": {
                "chief_complaint": {
                    "value": "fever",
                    "status": "answered",
                    "original_text": "बुखार",
                    "source_turn": 1,
                },
                # The hedge survives: this renders as approximate, and
                # "शायद दो हफ्ते" is printed beside it.
                "duration": {
                    "value": {"n": 2, "unit": "week"},
                    "status": "answered",
                    "original_text": "शायद दो हफ्ते",
                    "source_turn": 3,
                    "confidence": 0.72,
                },
                # Asked twice, never bound. Not `not_asked`, and not `no`.
                "severity": {"value": None, "status": "unresolved", "source_turn": 5},
                "current_medications": {"value": None, "status": "not_asked"},
                "drug_allergy": {"value": None, "status": "not_asked"},
            },
            "red_flags": [],
            "engine_version": "jetson-0.4.1",
            "content_version": "questions-2026-09-01",
        },
        {
            "schema_version": "0.1",
            "intake_id": "3f1c2a10-0000-4000-8000-000000000003",
            "kiosk_id": "kiosk-aiia-02",
            "hospital_id": HOSPITAL_ID,
            "started_at": (_BASE + timedelta(minutes=35)).isoformat(),
            "completed_at": (_BASE + timedelta(minutes=38)).isoformat(),
            # The device stopped the interview itself. The backend does not
            # re-evaluate the criterion; it records that it fired.
            "status": "aborted_red_flag",
            "language": "hi",
            "reporter": "self",
            "department_code": "general",
            "patient_ref": {"type": "guest"},
            "turns": [
                _turn(1, "ask_complaint", "सीने में दर्द", 0.95),
                _turn(4, "ask_breathlessness", "हाँ, साँस लेने में तकलीफ है", 0.89),
            ],
            "fields": {
                "chief_complaint": {
                    "value": "chest_pain",
                    "status": "answered",
                    "original_text": "सीने में दर्द",
                    "source_turn": 1,
                },
                "breathlessness": {
                    "value": True,
                    "status": "answered",
                    "original_text": "हाँ, साँस लेने में तकलीफ है",
                    "source_turn": 4,
                },
                "severity": {"value": 9, "status": "answered", "source_turn": 5},
                "duration": {"value": None, "status": "not_asked"},
            },
            "red_flags": [
                {
                    "rule_id": "RF_SEVERE_BREATHLESSNESS",
                    "fired_at_turn": 5,
                    "criteria_met": ["breathlessness=true", "severity>=8"],
                    "severity": "critical",
                    "label": "Severe breathlessness with high pain score",
                }
            ],
            "engine_version": "jetson-0.4.1",
            "content_version": "questions-2026-09-01",
        },
        {
            "schema_version": "0.1",
            "intake_id": "3f1c2a10-0000-4000-8000-000000000004",
            "kiosk_id": "kiosk-aiia-01",
            "hospital_id": HOSPITAL_ID,
            "started_at": (_BASE + timedelta(minutes=50)).isoformat(),
            "completed_at": (_BASE + timedelta(minutes=57)).isoformat(),
            "status": "complete",
            "language": "en",
            "reporter": "self",
            "department_code": "panchakarma",
            "patient_ref": {"type": "hospital_id", "value": "UHID-100518"},
            "turns": [
                _turn(1, "ask_complaint", "pain in both knees", 0.96),
                _turn(3, "ask_duration", "about six months", 0.94),
            ],
            "fields": {
                "chief_complaint": {
                    "value": "joint_pain",
                    "status": "answered",
                    "original_text": "pain in both knees",
                    "source_turn": 1,
                },
                "duration": {
                    "value": {"n": 6, "unit": "month"},
                    "status": "answered",
                    "original_text": "about six months",
                    "source_turn": 3,
                },
                "severity": {"value": 5, "status": "answered", "source_turn": 4},
                # Asked, and declined. A different thing again from unresolved.
                "tobacco": {"value": None, "status": "refused", "source_turn": 9},
                "pregnancy": {"value": None, "status": "not_applicable"},
                "known_hypertension": {"value": True, "status": "answered", "source_turn": 6},
                "current_medications": {
                    "value": "Amlodipine 5",
                    "status": "answered",
                    "source_turn": 7,
                },
            },
            "red_flags": [],
            "engine_version": "jetson-0.4.1",
            "content_version": "questions-2026-09-01",
        },
    ]


def app_visit_payloads(reference: str) -> list[dict[str, Any]]:
    """Two earlier visits taken in the app, filed under the phone reference.

    These are what makes the ABHA link visible rather than theoretical: they
    are reachable by phone and not by ABHA until a link row exists, and then by
    both. Filed under `phone` because that is how the app files an intake —
    `app/lib/submit/record.dart` sends the peppered HMAC as `patient_ref`.

    Older than the kiosk intakes above, so a merged history is obviously
    chronological rather than accidentally in order.
    """
    ref = {"type": "phone", "value": reference}
    return [
        {
            "schema_version": "0.1",
            "intake_id": "3f1c2a10-0000-4000-8000-0000000000a1",
            "kiosk_id": None,
            "hospital_id": HOSPITAL_ID,
            "started_at": (_BASE - timedelta(days=95)).isoformat(),
            "completed_at": (_BASE - timedelta(days=95) + timedelta(minutes=6)).isoformat(),
            "status": "complete",
            "language": "hi",
            "reporter": "self",
            "department_code": "kayachikitsa",
            "patient_ref": ref,
            "turns": [_turn(1, "ask_complaint", "घुटनों में दर्द", 0.92)],
            "fields": {
                "chief_complaint": {
                    "value": "joint_pain",
                    "status": "answered",
                    "original_text": "घुटनों में दर्द",
                    "source_turn": 1,
                },
                "duration": {
                    "value": {"n": 2, "unit": "month"},
                    "status": "answered",
                    "source_turn": 2,
                },
                "known_diabetes": {"value": True, "status": "answered", "source_turn": 4},
                "current_medications": {
                    "value": "Metformin 500",
                    "status": "answered",
                    "source_turn": 4,
                },
            },
            "red_flags": [],
            "engine_version": None,
            "content_version": "questions-2026-09-01",
        },
        {
            "schema_version": "0.1",
            "intake_id": "3f1c2a10-0000-4000-8000-0000000000a2",
            "kiosk_id": None,
            "hospital_id": HOSPITAL_ID,
            "started_at": (_BASE - timedelta(days=40)).isoformat(),
            "completed_at": (_BASE - timedelta(days=40) + timedelta(minutes=5)).isoformat(),
            "status": "complete",
            "language": "hi",
            "reporter": "self",
            "department_code": "kayachikitsa",
            "patient_ref": ref,
            "turns": [_turn(1, "ask_complaint", "पैर में चोट", 0.88)],
            "fields": {
                # Deliberately unrelated to today's abdominal pain. When the
                # timeline agent lands, this is the candidate it must decide to
                # leave out — the foot injury under a fever complaint.
                "chief_complaint": {
                    "value": "injury",
                    "status": "answered",
                    "original_text": "पैर में चोट",
                    "source_turn": 1,
                },
                "duration": {
                    "value": {"n": 2, "unit": "day"},
                    "status": "answered",
                    "source_turn": 2,
                },
            },
            "red_flags": [],
            "engine_version": None,
            "content_version": "questions-2026-09-01",
        },
    ]


async def seed(
    session: AsyncSession,
    *,
    terminology_dir: Path | None = None,
    clock: Clock | None = None,
    patient_ref_pepper: str | None = None,
) -> dict[str, Any]:
    """Create the hospital, the terminology tables and the sample intakes.

    Idempotent: an existing hospital short-circuits everything except its
    department list, which is reconciled. Departments are configuration rather
    than demo data — a row created once with four of them would otherwise keep
    four forever while the code says eight.

    `patient_ref_pepper` is what makes the app half of the demo work. The phone
    reference an intake is filed under is `HMAC(pepper, number)`, so the value
    is **different in every deployment** and must be computed here rather than
    written down: a hardcoded digest produces a patient whose history nobody
    can reach, silently, on any machine with a different pepper. With no pepper
    set the phone half is skipped and said so in the result — the seeded
    intakes and the ABHA link still land.
    """
    clock = clock or SystemClock()
    hospitals = HospitalRepository(session)

    existing = await hospitals.get(HOSPITAL_ID)
    if existing is not None:
        # Still a no-op for everything that is *demo data* — the sample
        # intakes, the ABHA link, the terminology rows all stay exactly as they
        # are, and re-running still cannot duplicate them.
        #
        # The department list is not demo data. It is configuration, and a
        # seeder that can never correct it means a hospital row created once
        # with four departments keeps four for the life of the database, while
        # the code, the display names and every developer's expectation say
        # eight. That gap is invisible until a patient needs the department
        # that is missing, which is the worst moment to discover it.
        if existing.departments != DEPARTMENTS:
            before = list(existing.departments)
            existing.departments = list(DEPARTMENTS)
            await session.flush()
            logger.info(
                "seed_departments_reconciled",
                hospital_id=HOSPITAL_ID,
                before=len(before),
                after=len(DEPARTMENTS),
            )
        logger.info("seed_skipped_existing")
        return {"hospital_id": HOSPITAL_ID, "created": False}

    await hospitals.create(
        hospital_id=HOSPITAL_ID,
        display_name="All India Institute of Ayurveda, New Delhi",
        location="New Delhi",
        departments=DEPARTMENTS,
        default_language="hi",
    )

    concepts = 0
    if terminology_dir is not None:
        concepts = await seed_terminology(TerminologyRepository(session), terminology_dir)

    patients = PatientRepository(session)
    links = PatientLinkRepository(session)
    with tenant_scope(HOSPITAL_ID):
        await patients.create(
            patient_id="pat_seed_0001",
            hospital_id=HOSPITAL_ID,
            external_mrn="UHID-100241",
            abha_address=DEMO_ABHA,
            display_name=None,
            preferred_language="hi",
        )
        await patients.create(
            patient_id="pat_seed_0002",
            hospital_id=HOSPITAL_ID,
            external_mrn="UHID-100518",
            abha_address=SECOND_ABHA,
            display_name=None,
            preferred_language="en",
        )

        service = IngestService(
            intakes=IntakeRepository(session),
            raw=IngestRawRepository(session),
            audit=AuditRepository(session),
            bus=InProcessBus(),
            clock=clock,
            ids=SequentialIdFactory(),
            repair_provider=None,
        )
        created: list[str] = []
        for payload in sample_payloads():
            result = await service.ingest(
                payload, hospital_id=HOSPITAL_ID, actor_id="seed"
            )
            if result.intake_id is None:
                # Our own fixtures failing their own contract is a broken
                # build, not a seeded demo. Surfacing it here beats a demo that
                # comes up with fewer intakes than it should and no reason why.
                raise RuntimeError(
                    f"seed payload was not usable ({result.reason}): {result.errors}"
                )
            created.append(result.intake_id)

        # The link rows. `(hospital_id, UHID)` and the ABHA address both point
        # at pat_seed_0001, so a history asked for under either comes back the
        # same — which is the thing the ABHA feature actually delivers, and it
        # does not work by setting `patients.abha_address` alone.
        now = clock.now()
        link_refs: list[tuple[str, str, str]] = [
            ("pat_seed_0001", "abha", DEMO_ABHA),
            ("pat_seed_0001", "hospital_id", "UHID-100241"),
            ("pat_seed_0002", "abha", SECOND_ABHA),
            ("pat_seed_0002", "hospital_id", "UHID-100518"),
        ]

        phone_linked = False
        phone_intakes: list[str] = []
        if patient_ref_pepper:
            # **Never hardcode this digest.** It is HMAC(pepper, number), so a
            # literal is wrong on every deployment with a different pepper and
            # produces a patient whose history nobody can reach.
            reference = phone_ref(DEMO_PHONE, pepper=patient_ref_pepper)
            for payload in app_visit_payloads(reference):
                result = await service.ingest(
                    payload, hospital_id=HOSPITAL_ID, actor_id="seed"
                )
                if result.intake_id is None:
                    raise RuntimeError(
                        f"seed payload was not usable ({result.reason}): {result.errors}"
                    )
                phone_intakes.append(result.intake_id)
            link_refs.append(("pat_seed_0001", "phone", reference))
            phone_linked = True
        else:
            logger.info("seed_phone_link_skipped", reason="no_patient_ref_pepper")

        for index, (patient_id, ref_type, ref_value) in enumerate(link_refs):
            await links.link(
                link_id=f"lnk_seed_{index:04d}",
                hospital_id=HOSPITAL_ID,
                patient_id=patient_id,
                ref_type=ref_type,
                ref_value=ref_value,
                source="seed",
                linked_at=now,
            )

    logger.info(
        "seed_complete",
        count=len(created) + len(phone_intakes),
        concepts=concepts,
        phone_linked=phone_linked,
    )
    return {
        "hospital_id": HOSPITAL_ID,
        "created": True,
        "departments": DEPARTMENTS,
        "intakes": created + phone_intakes,
        "terminology_concepts": concepts,
        # The demo script prints these. The number is invented; the reference
        # is not printed, because it identifies a patient.
        "demo_phone": DEMO_PHONE if phone_linked else None,
        "demo_abha": DEMO_ABHA,
        "phone_linked": phone_linked,
    }


def seeded_intake_ids() -> list[str]:
    """The ids the seeder produces, for tests and demo scripts."""
    return [str(intake_uuid(p["intake_id"])) for p in sample_payloads()]
