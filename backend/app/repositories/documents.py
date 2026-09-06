"""Document and extraction persistence.

The redaction assertion in `save_extraction` is the last line of defence: it
re-checks every string on its way to the database and refuses the write if
something identifier-shaped survived. The pass has already run in the OCR
adapter; this catches the path that skipped it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.domain.documents.extraction import (
    DocumentExtraction,
    DocumentItem,
    ItemKind,
    LabResult,
    Medicine,
    QualityVerdict,
    RangeStatus,
)
from app.domain.documents.redaction import contains_identifier
from app.domain.record import DocumentKind, DocumentStatus
from app.models.clinical import DocumentItemRecord, DocumentRecordRow


class RedactionEscape(ConflictError):
    """Identifier-shaped text reached the persistence boundary.

    A 500-shaped bug reported as a conflict, because the correct response is to
    stop the write, not to store it and log a warning. `tests/safety/
    test_redaction.py` asserts this fires.
    """

    code = "redaction_escape"


class DocumentRepository:
    """Reads and writes documents and their extracted items."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        document_id: str,
        hospital_id: str,
        intake_id: str,
        kind: DocumentKind,
        content_type: str,
        storage_key: str,
        byte_size: int,
        uploaded_at: datetime,
        demo: bool = False,
    ) -> DocumentRecordRow:
        row = DocumentRecordRow(
            id=document_id,
            hospital_id=hospital_id,
            intake_id=intake_id,
            kind=kind.value,
            status=DocumentStatus.RECEIVED.value,
            content_type=content_type,
            storage_key=storage_key,
            byte_size=byte_size,
            uploaded_at=uploaded_at,
            demo=demo,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, *, hospital_id: str, document_id: str) -> DocumentRecordRow:
        result = await self._session.execute(
            select(DocumentRecordRow).where(
                DocumentRecordRow.hospital_id == hospital_id,
                DocumentRecordRow.id == document_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"no document {document_id!r} at this hospital")
        return row

    async def for_intakes(
        self, *, hospital_id: str, intake_ids: Sequence[str]
    ) -> Sequence[DocumentRecordRow]:
        """Documents across several intakes, newest first.

        For a patient looking at their own document library, where the intakes
        are the ones their session resolves to. `hospital_id` is in the outer
        WHERE for the tenancy guard, and the intake list is what scopes it to
        one patient — a caller cannot widen it by asking, because they never
        supply it.
        """
        if not intake_ids:
            return []
        result = await self._session.execute(
            select(DocumentRecordRow)
            .where(
                DocumentRecordRow.hospital_id == hospital_id,
                DocumentRecordRow.intake_id.in_(list(intake_ids)),
            )
            .order_by(DocumentRecordRow.uploaded_at.desc())
        )
        return list(result.scalars())

    async def for_intake(
        self, *, hospital_id: str, intake_id: str
    ) -> Sequence[DocumentRecordRow]:
        result = await self._session.execute(
            select(DocumentRecordRow)
            .where(
                DocumentRecordRow.hospital_id == hospital_id,
                DocumentRecordRow.intake_id == intake_id,
            )
            .order_by(DocumentRecordRow.uploaded_at)
        )
        return list(result.scalars())

    async def mark_processing(self, *, hospital_id: str, document_id: str) -> None:
        row = await self.get(hospital_id=hospital_id, document_id=document_id)
        row.status = DocumentStatus.PROCESSING.value
        await self._session.flush()

    async def mark_failed(
        self, *, hospital_id: str, document_id: str, reason: str
    ) -> None:
        row = await self.get(hospital_id=hospital_id, document_id=document_id)
        row.status = DocumentStatus.FAILED.value
        row.rejection_reason = reason
        await self._session.flush()

    async def save_extraction(
        self,
        extraction: DocumentExtraction,
        *,
        hospital_id: str,
        intake_id: str,
        processed_at: datetime,
    ) -> DocumentRecordRow:
        """Persist an extraction and its items.

        Every string is checked for identifier shapes first. If one survived
        redaction, nothing is written — a partially-redacted document in the
        database is a leak that looks like a success.
        """
        _assert_redacted(extraction)

        row = await self.get(hospital_id=hospital_id, document_id=extraction.document_id)
        row.kind = extraction.kind.value
        row.page_count = extraction.page_count
        row.overall_confidence = extraction.overall_confidence
        row.low_confidence = extraction.low_confidence
        row.page_text = list(extraction.page_text)
        row.redactions = dict(extraction.redactions)
        row.provider = extraction.provider
        row.model_id = extraction.model_id
        row.demo = extraction.demo
        row.document_date = extraction.document_date
        row.issuing_facility = extraction.issuing_facility
        row.processed_at = processed_at

        if extraction.quality is QualityVerdict.REJECTED:
            row.status = DocumentStatus.REJECTED_QUALITY.value
            row.rejection_reason = extraction.quality_reason
            await self._session.flush()
            return row

        row.status = DocumentStatus.PROCESSED.value
        row.rejection_reason = None

        for item in extraction.items:
            payload = None
            if item.medicine is not None:
                payload = item.medicine.model_dump(mode="json")
            elif item.lab_result is not None:
                payload = item.lab_result.model_dump(mode="json")
            self._session.add(
                DocumentItemRecord(
                    id=item.item_id,
                    hospital_id=hospital_id,
                    document_id=extraction.document_id,
                    intake_id=intake_id,
                    kind=item.kind.value,
                    raw_text=item.raw_text,
                    page=item.page,
                    bbox=item.bbox.model_dump(mode="json") if item.bbox else None,
                    confidence=item.confidence,
                    needs_verification=item.needs_verification,
                    label=item.label,
                    payload=payload,
                    range_status=item.range_status.value,
                )
            )
        await self._session.flush()
        return row

    async def items_for_intake(
        self, *, hospital_id: str, intake_id: str
    ) -> Sequence[DocumentItemRecord]:
        result = await self._session.execute(
            select(DocumentItemRecord)
            .where(
                DocumentItemRecord.hospital_id == hospital_id,
                DocumentItemRecord.intake_id == intake_id,
            )
            .order_by(DocumentItemRecord.document_id, DocumentItemRecord.id)
        )
        return list(result.scalars())


    async def extractions_for_intake(
        self, *, hospital_id: str, intake_id: str
    ) -> tuple[DocumentExtraction, ...]:
        """Rebuild every stored extraction for an intake.

        The stored rows are the source of truth, not a cached extraction object:
        what is read back reflects what is in the database, including anything a
        later migration changed.
        """
        documents = await self.for_intake(hospital_id=hospital_id, intake_id=intake_id)
        items = await self.items_for_intake(hospital_id=hospital_id, intake_id=intake_id)
        by_document: dict[str, list[DocumentItemRecord]] = {}
        for item in items:
            by_document.setdefault(item.document_id, []).append(item)
        return tuple(
            _extraction_from_row(row, by_document.get(row.id, [])) for row in documents
        )

    async def extraction_for(
        self, *, hospital_id: str, document_id: str
    ) -> DocumentExtraction:
        """Rebuild one stored extraction. What a replayed read returns."""
        row = await self.get(hospital_id=hospital_id, document_id=document_id)
        items = [
            item
            for item in await self.items_for_intake(
                hospital_id=hospital_id, intake_id=row.intake_id
            )
            if item.document_id == document_id
        ]
        return _extraction_from_row(row, items)


def _extraction_from_row(
    row: DocumentRecordRow, items: Sequence[DocumentItemRecord]
) -> DocumentExtraction:
    return DocumentExtraction(
        document_id=row.id,
        kind=DocumentKind(row.kind),
        page_count=row.page_count,
        items=[_item_from_row(i) for i in items],
        page_text=list(row.page_text or []),
        overall_confidence=row.overall_confidence or 0.0,
        document_date=row.document_date,
        issuing_facility=row.issuing_facility,
        redactions=dict(row.redactions or {}),
        provider=row.provider,
        model_id=row.model_id,
        demo=row.demo,
    )


def _item_from_row(row: DocumentItemRecord) -> DocumentItem:
    kind = ItemKind(row.kind)
    medicine = (
        Medicine.model_validate(row.payload)
        if kind is ItemKind.MEDICINE and row.payload
        else None
    )
    lab = (
        LabResult.model_validate(row.payload)
        if kind is ItemKind.LAB_RESULT and row.payload
        else None
    )
    return DocumentItem(
        item_id=row.id,
        kind=kind,
        raw_text=row.raw_text,
        page=row.page,
        bbox=row.bbox,
        confidence=row.confidence,
        needs_verification=row.needs_verification,
        medicine=medicine,
        lab_result=lab,
        label=row.label,
        range_status=RangeStatus(row.range_status),
    )


def _assert_redacted(extraction: DocumentExtraction) -> None:
    """Refuse to persist anything identifier-shaped."""
    offenders: list[str] = []
    for index, page in enumerate(extraction.page_text):
        if contains_identifier(page):
            offenders.append(f"page_text[{index}]")
    for item in extraction.items:
        if contains_identifier(item.raw_text):
            offenders.append(f"item {item.item_id}")
        if item.label and contains_identifier(item.label):
            offenders.append(f"item {item.item_id} label")
        if item.medicine is not None and contains_identifier(item.medicine.name):
            offenders.append(f"item {item.item_id} medicine")
    if extraction.issuing_facility and contains_identifier(extraction.issuing_facility):
        offenders.append("issuing_facility")
    if offenders:
        # The locations, never the values. This message reaches a log.
        raise RedactionEscape(
            "identifier-shaped text survived redaction and was not written",
            details={"document_id": extraction.document_id, "locations": offenders},
        )
