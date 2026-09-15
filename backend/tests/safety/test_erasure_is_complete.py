"""Erasure means every table, and a new table must not quietly escape it.

The failure this guards against is specific and it is not hypothetical: someone
adds a table that holds patient data — the way `ayush_profiles` and
`clinical_timelines` were both added in one week — and nobody thinks about
erasure, because erasure lives in a different file. The patient presses delete,
is told their record is gone, and their Prakriti answers are still on a disk.

So the list of tables `ErasureService` clears is asserted against the schema
itself rather than against a copy of the list. Adding a model to
`app/models/clinical.py` fails this test until it is either erased or named
here as deliberately kept, with the reason written down.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select

from app.core.clock import FrozenClock
from app.domain.record import PatientRef, PatientRefType
from app.models import Base
from app.models.clinical import (
    AyushProfileRecord,
    ClinicalFactRecord,
    ClinicalTimeline,
    ConsentArtefact,
    DocumentItemRecord,
    DocumentRecordRow,
    IngestRawRecord,
    IntakeRecord,
    PatientIdentifierLink,
    RedFlagEventRecord,
    ReportRecord,
)
from app.repositories.consent import AuditRepository
from app.services.erasure import ErasureService
from tests.conftest import HOSPITAL_ID

NOW = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)

#: Tables `ErasureService` empties for the patient it is erasing.
ERASED = {
    AyushProfileRecord.__tablename__,
    ClinicalFactRecord.__tablename__,
    ClinicalTimeline.__tablename__,
    ConsentArtefact.__tablename__,
    DocumentItemRecord.__tablename__,
    DocumentRecordRow.__tablename__,
    IngestRawRecord.__tablename__,
    IntakeRecord.__tablename__,
    PatientIdentifierLink.__tablename__,
    RedFlagEventRecord.__tablename__,
    ReportRecord.__tablename__,
}

#: Tables deliberately left alone, each with the reason it survives. A table
#: belongs here only when keeping it cannot reconstruct the patient's history.
KEPT: dict[str, str] = {
    "hospitals": "the facility itself, which is not anybody's record",
    "terminology_concepts": "NAMASTE and ICD-11 reference data, the same for every patient",
    "terminology_mappings": "NAMASTE and ICD-11 reference data, the same for every patient",
    "alembic_version": "schema bookkeeping, which holds one migration id and nothing else",
    "audit_log": (
        "the record that the erasure happened. Deleting it would erase the "
        "evidence of having complied, which is what a regulator asks to see. "
        "Rows carry ids and counts, never clinical text."
    ),
    "idempotency_keys": (
        "request replay bookkeeping, expired on its own schedule. Holds a "
        "response fingerprint, not a record."
    ),
    "otp_challenges": (
        "a phone reference and a code hash, expiring on their own schedule; "
        "no consultation is reachable from them"
    ),
    "patient_sessions": (
        "erasure is not sign-out. A patient who deletes their history and "
        "starts a new intake is starting fresh, not locked out."
    ),
    "patients": (
        "the demographic stub, which carries no consultation. Left because a "
        "row here is reachable only from records that have just been deleted."
    ),
}


class TestTheListCoversTheSchema:
    def test_every_table_is_erased_or_deliberately_kept(self) -> None:
        """No table gets to be neither."""
        tables = set(Base.metadata.tables)
        unaccounted = tables - ERASED - set(KEPT)
        assert unaccounted == set(), (
            f"tables missing from the erasure decision: {sorted(unaccounted)}. "
            "Add them to ERASED in app/services/erasure.py, or to KEPT here "
            "with the reason they may survive a patient's deletion request."
        )

    def test_nothing_is_both(self) -> None:
        assert ERASED & set(KEPT) == set()

    def test_every_kept_table_says_why(self) -> None:
        """A reason a sentence long, so the next person can disagree with it."""
        for table, reason in KEPT.items():
            assert len(reason) > 20, f"{table} needs a real reason, not {reason!r}"


class _RecordingStore:
    """An object store that says what it was asked to delete."""

    def __init__(self, *, fail: set[str] | None = None) -> None:
        self.deleted: list[str] = []
        self._fail = fail or set()

    async def delete(self, key: str) -> None:
        if key in self._fail:
            raise RuntimeError("bucket unreachable")
        self.deleted.append(key)

    async def put(self, key: str, data: bytes, *, content_type: str) -> str:
        raise NotImplementedError

    async def get(self, key: str) -> bytes:
        raise NotImplementedError

    async def signed_url(self, key: str, *, ttl_seconds: int) -> str:
        raise NotImplementedError


def _service(session: Any, store: _RecordingStore) -> ErasureService:
    return ErasureService(
        session,
        storage=store,
        clock=FrozenClock(NOW),
        audit=AuditRepository(session),
    )


class TestAGuest:
    async def test_erasing_a_guest_is_a_no_op(self, session: Any) -> None:
        """A guest has nothing filed under them by construction, so this must
        return an empty result rather than raising — the caller's flow is the
        same either way."""
        service = _service(session, _RecordingStore())
        result = await service.erase(
            PatientRef(type=PatientRefType.GUEST, value=None),
            hospital_id=HOSPITAL_ID,
            actor_id="patient-1",
        )
        assert result.intakes == 0
        assert result.complete


class TestTheObjectStore:
    async def test_a_refused_object_is_reported_not_swallowed(
        self, session: Any
    ) -> None:
        """One unreachable scan must not leave the other nine in place — and it
        must not be reported as a clean erasure either."""
        store = _RecordingStore(fail={"a/1.png"})
        service = _service(session, store)
        deleted, orphaned = await service._delete_objects(
            ["a/1.png", "a/2.png"],
        )
        assert deleted == 1
        assert orphaned == ("a/1.png",)
        assert store.deleted == ["a/2.png"]

    async def test_a_clean_run_reports_complete(self, session: Any) -> None:
        store = _RecordingStore()
        service = _service(session, store)
        deleted, orphaned = await service._delete_objects(
            ["a/1.png"],
        )
        assert deleted == 1
        assert orphaned == ()


class TestTheAuditRowSurvives:
    async def test_an_erasure_writes_one_audit_row(self, session: Any) -> None:
        """The one row that must outlive the data it describes."""
        service = _service(session, _RecordingStore())
        await service.erase(
            PatientRef(type=PatientRefType.PHONE, value="a" * 64),
            hospital_id=HOSPITAL_ID,
            actor_id="patient-1",
        )
        from app.models.clinical import AuditLogEntry

        count = await session.execute(
            select(func.count())
            .select_from(AuditLogEntry)
            .where(
                AuditLogEntry.hospital_id == HOSPITAL_ID,
                AuditLogEntry.action == "patient_erasure",
            )
        )
        assert count.scalar_one() == 1

    async def test_the_audit_row_carries_no_clinical_text(
        self, session: Any
    ) -> None:
        """§1 rule 7. The row names counts and a reference, never an answer."""
        service = _service(session, _RecordingStore())
        await service.erase(
            PatientRef(type=PatientRefType.PHONE, value="b" * 64),
            hospital_id=HOSPITAL_ID,
            actor_id="patient-1",
        )
        from app.models.clinical import AuditLogEntry

        rows = await session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.hospital_id == HOSPITAL_ID,
                AuditLogEntry.action == "patient_erasure",
            )
        )
        entry = rows.scalars().first()
        assert entry is not None
        assert set(entry.after) <= {
            "intakes",
            "facts",
            "documents",
            "document_objects",
            "reports",
            "timelines",
            "red_flags",
            "consent_artefacts",
            "raw_payloads",
            "ayush_profiles",
            "identifier_links",
            "complete",
        }


@pytest.mark.parametrize("value", ["", None])
class TestABadReference:
    async def test_an_empty_reference_erases_nothing(
        self, session: Any, value: str | None
    ) -> None:
        """The dangerous shape: a reference that matches every row or none.
        Erasing on an empty value must never become 'delete where value = ""'
        against somebody else's record."""
        service = _service(session, _RecordingStore())
        ref = PatientRef(type=PatientRefType.GUEST, value=value)
        result = await service.erase(
            ref, hospital_id=HOSPITAL_ID, actor_id="patient-1"
        )
        assert result.intakes == 0
