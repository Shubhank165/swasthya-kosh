"""Erasing a patient's record at one hospital, on their own instruction.

`consent_v1.yaml` already promises this in the notice every patient is shown:

    "You can ask us to delete what we recorded, at the registration desk, at
    any time before or after your consultation."

Until now that promise had no implementation behind it — there is no other
delete path anywhere in this service. This module is the promise kept, and the
app's Profile screen is the registration desk moved to the patient's pocket.

**What "my history" means here is every table, not the interesting ones.**
An erasure that leaves facts behind in `clinical_facts` because somebody
listed the tables from memory is worse than no erasure: the patient is told
their record is gone and it is not. The order below is the foreign-key order,
children first, and every table that carries a row keyed to an intake appears
in it. `tests/safety/test_erasure_is_complete.py` fails if a new table is added
to the schema and not to this list — the test is the guard, not this docstring.

**Three things deliberately survive.**

*The audit log.* It is the record that the erasure happened, who asked, and
what went. Deleting it would erase the evidence of complying with the request,
which is the one thing a regulator will ask to see. Its rows name an intake id
and a count; they carry no clinical text (§1 rule 7), so keeping them does not
keep the history.

*The hospital's own aggregate counters.* `correction_rate` and friends read
`physician_action` across facts; those facts go, so the numbers move. Nothing
is retained to hold them steady, and that is correct — a metric is not a reason
to keep somebody's consultation.

*The patient's sign-in.* Erasure is not sign-out. A patient who deletes their
history and then starts a new intake is a patient starting fresh, not a patient
locked out. `patient_sessions` holds a phone reference and a token and no
clinical content at all.

**Scoped to one hospital**, like every other query in this service. A patient
signed in at AIIA Delhi erases what AIIA Delhi holds. Reaching across tenants
would require a cross-tenant query, which `app/db/tenancy.py` raises on — so
this is enforced by the same guard as everything else rather than by care.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.protocols import ObjectStore
from app.core.clock import Clock
from app.core.logging import get_logger
from app.domain.record import PatientRef, PatientRefType
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
from app.repositories.patients import PatientLinkRepository

logger = get_logger(__name__)


#: The tables whose rows belong to one intake at one hospital, and so all
#: delete the same way. Spelled as a union of the real models rather than a
#: bare `type`, so handing `_delete_by_intake` a table that is keyed some other
#: way — `ayush_profiles`, say, which is keyed to the person — is a type error
#: rather than a delete that silently matches nothing.
_IntakeScoped = (
    type[ClinicalFactRecord]
    | type[ClinicalTimeline]
    | type[DocumentRecordRow]
    | type[RedFlagEventRecord]
    | type[ReportRecord]
)


@dataclass(frozen=True)
class ErasureResult:
    """What went, by table. Returned to the app so it can say so rather than
    claim success in the abstract — "3 visits and 2 documents deleted" is a
    sentence a patient can check against what they remember."""

    intakes: int = 0
    facts: int = 0
    documents: int = 0
    document_objects: int = 0
    reports: int = 0
    timelines: int = 0
    red_flags: int = 0
    consent_artefacts: int = 0
    raw_payloads: int = 0
    ayush_profiles: int = 0
    identifier_links: int = 0
    #: Storage keys the object store refused to delete. Non-empty means bytes
    #: survive in a bucket after the rows are gone, which the caller must not
    #: report as a clean erasure.
    orphaned_objects: tuple[str, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        return not self.orphaned_objects

    def to_dict(self) -> dict[str, object]:
        return {
            "intakes": self.intakes,
            "facts": self.facts,
            "documents": self.documents,
            "document_objects": self.document_objects,
            "reports": self.reports,
            "timelines": self.timelines,
            "red_flags": self.red_flags,
            "consent_artefacts": self.consent_artefacts,
            "raw_payloads": self.raw_payloads,
            "ayush_profiles": self.ayush_profiles,
            "identifier_links": self.identifier_links,
            "complete": self.complete,
        }


class ErasureService:
    """Deletes everything one hospital holds about one patient."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: ObjectStore,
        clock: Clock,
        audit: AuditRepository,
        links: PatientLinkRepository | None = None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._clock = clock
        self._audit = audit
        self._links = links

    async def erase(
        self, ref: PatientRef, *, hospital_id: str, actor_id: str
    ) -> ErasureResult:
        """Erase everything filed under `ref` — and under every reference that
        resolves to the same person.

        The alias expansion is the same one `IdentityService.history` uses, and
        for the same reason: a patient who signed in by phone and later linked
        an ABHA address has one history under two references. Deleting only the
        reference they happen to be holding would leave the other half behind
        and report success.
        """
        if ref.type is PatientRefType.GUEST or ref.value is None:
            # A guest has nothing filed under them by construction. Returning an
            # empty result rather than raising keeps the caller's flow identical
            # either way.
            return ErasureResult()

        refs = await self._refs_for(ref, hospital_id=hospital_id)
        intake_ids = await self._intake_ids(refs, hospital_id=hospital_id)

        result = await self._erase_intakes(intake_ids, hospital_id=hospital_id)
        result = await self._erase_patient_level(
            result, refs, hospital_id=hospital_id
        )

        # One audit row for the whole erasure, written last so it records what
        # actually went rather than what was about to. It names counts and
        # intake ids; it carries no clinical text.
        await self._audit.write(
            hospital_id=hospital_id,
            occurred_at=self._clock.now(),
            actor_id=actor_id,
            actor_role="patient",
            action="patient_erasure",
            entity_type="patient_ref",
            entity_id=f"{ref.type.value}:{ref.value}",
            after=result.to_dict(),
            reason="patient requested erasure of their own record",
        )

        logger.info(
            "patient_erasure",
            hospital_id=hospital_id,
            intakes=result.intakes,
            facts=result.facts,
            documents=result.documents,
            complete=result.complete,
        )
        return result

    async def _refs_for(
        self, ref: PatientRef, *, hospital_id: str
    ) -> tuple[tuple[str, str], ...]:
        assert ref.value is not None
        me = ((ref.type.value, ref.value),)
        if self._links is None:
            return me
        return await self._links.aliases_for(
            ref_type=ref.type.value, ref_value=ref.value, hospital_id=hospital_id
        )

    async def _intake_ids(
        self, refs: tuple[tuple[str, str], ...], *, hospital_id: str
    ) -> list[str]:
        if not refs:
            return []
        from sqlalchemy import and_, or_

        clauses = [
            and_(
                IntakeRecord.patient_ref_type == ref_type,
                IntakeRecord.patient_ref_value == ref_value,
            )
            for ref_type, ref_value in refs
        ]
        rows = await self._session.execute(
            select(IntakeRecord.id).where(
                IntakeRecord.hospital_id == hospital_id, or_(*clauses)
            )
        )
        return [row[0] for row in rows.all()]

    async def _erase_intakes(
        self, intake_ids: list[str], *, hospital_id: str
    ) -> ErasureResult:
        """Children before parents, and bytes before rows.

        The object store is emptied *before* the document rows go, because the
        storage key lives on the row: delete the row first and the bytes are
        unreachable and undeletable, which is the one failure here that cannot
        be retried.
        """
        if not intake_ids:
            return ErasureResult()

        document_ids, keys = await self._document_keys(
            intake_ids, hospital_id=hospital_id
        )
        deleted_objects, orphaned = await self._delete_objects(keys)

        items = 0
        if document_ids:
            items = await self._delete_where(
                DocumentItemRecord, DocumentItemRecord.document_id.in_(document_ids)
            )

        documents = await self._delete_by_intake(
            DocumentRecordRow, intake_ids, hospital_id
        )
        facts = await self._delete_by_intake(
            ClinicalFactRecord, intake_ids, hospital_id
        )
        red_flags = await self._delete_by_intake(
            RedFlagEventRecord, intake_ids, hospital_id
        )
        reports = await self._delete_by_intake(ReportRecord, intake_ids, hospital_id)
        timelines = await self._delete_by_intake(
            ClinicalTimeline, intake_ids, hospital_id
        )
        consents = await self._delete_where(
            ConsentArtefact,
            ConsentArtefact.hospital_id == hospital_id,
            ConsentArtefact.intake_id.in_(intake_ids),
        )
        # `ingest_raw` is keyed by the intake id the payload *claimed*, not a
        # foreign key — an unparseable payload may never have produced an
        # intake row. It holds whole submitted bodies, so leaving it behind
        # would leave the patient's own words in the one table that stores them
        # unstructured.
        raw = await self._delete_where(
            IngestRawRecord,
            IngestRawRecord.hospital_id == hospital_id,
            IngestRawRecord.claimed_intake_id.in_(intake_ids),
        )
        intakes = await self._delete_where(
            IntakeRecord,
            IntakeRecord.hospital_id == hospital_id,
            IntakeRecord.id.in_(intake_ids),
        )

        logger.info("erasure_document_items", count=items)
        return ErasureResult(
            intakes=intakes,
            facts=facts,
            documents=documents,
            document_objects=deleted_objects,
            reports=reports,
            timelines=timelines,
            red_flags=red_flags,
            consent_artefacts=consents,
            raw_payloads=raw,
            orphaned_objects=orphaned,
        )

    async def _erase_patient_level(
        self,
        result: ErasureResult,
        refs: tuple[tuple[str, str], ...],
        *,
        hospital_id: str,
    ) -> ErasureResult:
        """The two tables keyed to the person rather than to a visit.

        The AYUSH profile is the clearest case for erasure in the whole
        service: it is answered once, is about the person rather than any
        consultation, and outlives every visit. A patient who deletes their
        history and keeps their Prakriti answers has not deleted their history.
        """
        from sqlalchemy import and_, or_

        if not refs:
            return result

        profile_clauses = [
            and_(
                AyushProfileRecord.patient_ref_type == ref_type,
                AyushProfileRecord.patient_ref_value == ref_value,
            )
            for ref_type, ref_value in refs
        ]
        profiles = await self._delete_where(
            AyushProfileRecord,
            AyushProfileRecord.hospital_id == hospital_id,
            or_(*profile_clauses),
        )

        link_clauses = [
            and_(
                PatientIdentifierLink.ref_type == ref_type,
                PatientIdentifierLink.ref_value == ref_value,
            )
            for ref_type, ref_value in refs
        ]
        links = await self._delete_where(
            PatientIdentifierLink,
            PatientIdentifierLink.hospital_id == hospital_id,
            or_(*link_clauses),
        )

        return ErasureResult(
            intakes=result.intakes,
            facts=result.facts,
            documents=result.documents,
            document_objects=result.document_objects,
            reports=result.reports,
            timelines=result.timelines,
            red_flags=result.red_flags,
            consent_artefacts=result.consent_artefacts,
            raw_payloads=result.raw_payloads,
            ayush_profiles=profiles,
            identifier_links=links,
            orphaned_objects=result.orphaned_objects,
        )

    async def _document_keys(
        self, intake_ids: list[str], *, hospital_id: str
    ) -> tuple[list[str], list[str]]:
        rows = await self._session.execute(
            select(DocumentRecordRow.id, DocumentRecordRow.storage_key).where(
                DocumentRecordRow.hospital_id == hospital_id,
                DocumentRecordRow.intake_id.in_(intake_ids),
            )
        )
        pairs = rows.all()
        return [row[0] for row in pairs], [row[1] for row in pairs if row[1]]

    async def _delete_objects(self, keys: list[str]) -> tuple[int, tuple[str, ...]]:
        """Scanned prescriptions and lab reports are the most identifying thing
        this service holds — a photograph of a document with a name on it.

        A failure here is collected rather than raised: one unreachable object
        must not leave the other nine and every database row in place. The
        caller is told which keys survived, and `complete` is false.
        """
        deleted = 0
        orphaned: list[str] = []
        for key in keys:
            try:
                await self._storage.delete(key)
                deleted += 1
            except Exception:
                logger.warning("erasure_object_not_deleted", storage_key=key)
                orphaned.append(key)
        return deleted, tuple(orphaned)

    async def _delete_by_intake(
        self, model: _IntakeScoped, intake_ids: list[str], hospital_id: str
    ) -> int:
        """Every table whose rows belong to an intake deletes the same way.

        The protocol above is what lets this stay one method: mypy checks that
        whatever is passed really does carry `hospital_id` and `intake_id`, so a
        model that does not cannot be handed to it by mistake.
        """
        return await self._delete_where(
            model,
            model.hospital_id == hospital_id,
            model.intake_id.in_(intake_ids),
        )

    async def _delete_where(
        self, model: type[Any] | _IntakeScoped, *clauses: ColumnElement[bool]
    ) -> int:
        result = await self._session.execute(delete(model).where(*clauses))
        return cast("CursorResult[Any]", result).rowcount or 0
