"""Documents and OCR — §6.

Two entry paths, identical downstream:

```
POST /api/v1/intakes/{id}/documents          # image, backend does OCR
POST /api/v1/intakes/{id}/documents/results  # OCR already done on the Jetson
```

The second exists because PP-OCRv5 Devanagari is 7.5 MB and Surya fits in
1.47 GB — on-device OCR is viable, and a hospital may prefer that images never
leave the building. Both paths produce identical document facts, which is only
true because both go through `_ingest_extraction` below.

**Processing is asynchronous, always.** Upload returns as soon as the image is
in object storage. Nothing about the patient's experience waits on a model:
they have already answered the questions, and the doctor sees the document
section fill in when it fills in.

The pipeline:

```
upload → object storage → queue → worker
   → quality gate (reject blurry, ask for reshoot)
   → classify: prescription | lab_report | discharge_summary | other
   → read → structured facts + bbox + confidence
   → redact identifiers → persist → emit document.processed
```
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from app.adapters.protocols import ObjectStore, OCRProvider
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.core.ids import IdFactory
from app.core.logging import get_logger
from app.domain.clinical.enums import Certainty, Section
from app.domain.documents.extraction import (
    DocumentExtraction,
    DocumentItem,
    ItemKind,
    QualityVerdict,
)
from app.domain.documents.ingredients import IngredientIndex
from app.domain.documents.interactions import (
    InteractionFinding,
    InteractionTable,
    MedicineEntry,
)
from app.domain.documents.labs import classify
from app.domain.record import (
    Coded,
    DocumentKind,
    DocumentSource,
    DocumentStatus,
    Fact,
    FactChannel,
    FieldStatus,
    Quantity,
    Text,
)
from app.events.bus import EventBus
from app.events.schemas import Event, EventName
from app.repositories.documents import DocumentRepository
from app.repositories.intakes import IntakeRepository

logger = get_logger(__name__)

#: Suffix by content type, for the storage key.
_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

ACCEPTED_CONTENT_TYPES = frozenset(_SUFFIXES)

#: Above this, an upload is refused before it reaches storage. A photograph of a
#: prescription is under a megabyte; anything at this size is a mistake or an
#: attack.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class UploadResult:
    document_id: str
    status: str
    #: Short-lived. Never public.
    url: str | None = None
    demo: bool = False


class DocumentService:
    """Upload, OCR, and turning an extraction into document-channel facts."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        intakes: IntakeRepository,
        storage: ObjectStore,
        ocr: OCRProvider,
        bus: EventBus,
        clock: Clock,
        ids: IdFactory,
        interactions: InteractionTable,
        ingredients: IngredientIndex,
        confidence_floor: float = 0.85,
        signed_url_ttl: int = 300,
        demo: bool = False,
    ) -> None:
        self._documents = documents
        self._intakes = intakes
        self._storage = storage
        self._ocr = ocr
        self._bus = bus
        self._clock = clock
        self._ids = ids
        self._interactions = interactions
        self._ingredients = ingredients
        self._floor = confidence_floor
        self._ttl = signed_url_ttl
        self._demo = demo

    # --- upload -------------------------------------------------------------

    async def upload(
        self,
        *,
        hospital_id: str,
        intake_id: str,
        content: bytes,
        content_type: str,
        kind: DocumentKind = DocumentKind.OTHER,
    ) -> UploadResult:
        """Store the image and register the document. Does not read it."""
        from app.adapters.storage.stores import object_key
        from app.core.errors import ValidationError

        if content_type not in ACCEPTED_CONTENT_TYPES:
            raise ValidationError(
                f"unsupported content type {content_type!r}",
                details={"accepted": sorted(ACCEPTED_CONTENT_TYPES)},
            )
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValidationError(
                "document exceeds the maximum upload size",
                details={"max_bytes": MAX_UPLOAD_BYTES},
            )
        # Confirms the intake exists *and* belongs to this hospital before
        # anything is written.
        await self._intakes.get_row(hospital_id=hospital_id, intake_id=intake_id)

        now = self._clock.now()
        document_id = self._ids.new_id("doc")
        key = object_key(hospital_id, intake_id, document_id, _SUFFIXES[content_type])
        await self._storage.put(key, content, content_type=content_type)
        await self._documents.create(
            document_id=document_id,
            hospital_id=hospital_id,
            intake_id=intake_id,
            kind=kind,
            content_type=content_type,
            storage_key=key,
            byte_size=len(content),
            uploaded_at=now,
            demo=self._demo,
        )
        await self._bus.publish(
            Event(
                name=EventName.DOCUMENT_UPLOADED,
                occurred_at=now,
                intake_id=intake_id,
                document_id=document_id,
                payload={"kind": kind.value, "byte_size": len(content)},
            )
        )
        return UploadResult(document_id=document_id, status="received", demo=self._demo)

    async def signed_url(self, *, hospital_id: str, document_id: str) -> str:
        row = await self._documents.get(hospital_id=hospital_id, document_id=document_id)
        return await self._storage.signed_url(row.storage_key, ttl_seconds=self._ttl)

    async def list_for_intakes(
        self, *, hospital_id: str, intake_ids: Sequence[str]
    ) -> Sequence[Any]:
        """Document rows across several intakes, newest first."""
        return await self._documents.for_intakes(
            hospital_id=hospital_id, intake_ids=intake_ids
        )

    async def list_for_intake(self, *, hospital_id: str, intake_id: str) -> Sequence[Any]:
        """Document rows for an intake, newest last."""
        return await self._documents.for_intake(
            hospital_id=hospital_id, intake_id=intake_id
        )

    async def content(self, *, hospital_id: str, key: str) -> bytes:
        """Raw bytes for a stored object.

        The caller must have already established that `key` belongs to
        `hospital_id`; the prefix check lives in the router because that is
        where the principal is.
        """
        if not key.startswith(f"{hospital_id}/"):
            raise NotFoundError("no such document")
        return await self._storage.get(key)

    # --- processing ---------------------------------------------------------

    async def process(self, *, hospital_id: str, document_id: str) -> DocumentExtraction:
        """Read a stored document. Runs on the worker, never in the request.

        **Idempotent.** A document that has already been read is returned as it
        was stored, and no OCR call is made. Pub/Sub delivers at least once, so
        a redelivery is expected rather than exceptional — and without this a
        second delivery duplicated every extracted line, which surfaces as five
        medicines on a report where the prescription printed five.

        `rejected_quality` is settled too: the image failed the quality gate and
        the patient has been asked to reshoot. Reading it again produces the same
        rejection and costs a model call. `failed` is *not* settled — that is
        the transient case, and retrying it is the entire point of a retry.
        """
        row = await self._documents.get(hospital_id=hospital_id, document_id=document_id)
        settled = {DocumentStatus.PROCESSED.value, DocumentStatus.REJECTED_QUALITY.value}
        if row.status in settled:
            logger.info(
                "document_already_processed",
                document_id=document_id,
                status=row.status,
            )
            return await self._documents.extraction_for(
                hospital_id=hospital_id, document_id=document_id
            )
        await self._documents.mark_processing(
            hospital_id=hospital_id, document_id=document_id
        )
        content = await self._storage.get(row.storage_key)
        extraction = await self._ocr.read(
            content, document_id=document_id, hint=DocumentKind(row.kind)
        )
        return await self._ingest_extraction(
            extraction, hospital_id=hospital_id, intake_id=row.intake_id
        )

    async def accept_results(
        self, *, hospital_id: str, intake_id: str, extraction: DocumentExtraction
    ) -> DocumentExtraction:
        """Take an extraction the Jetson produced on-device.

        The image never arrives, so there is no storage key and no signed URL —
        the evidence panel shows the bounding boxes against a page the device
        holds. Everything downstream is identical to the cloud path.
        """
        from app.adapters.storage.stores import object_key

        await self._intakes.get_row(hospital_id=hospital_id, intake_id=intake_id)
        await self._documents.create(
            document_id=extraction.document_id,
            hospital_id=hospital_id,
            intake_id=intake_id,
            kind=extraction.kind,
            content_type="application/json",
            # A key that resolves to nothing, on purpose: the row records where
            # the image *would* live so a later upload can fill it in, and the
            # storage layer returns a 404 rather than a wrong image.
            storage_key=object_key(hospital_id, intake_id, extraction.document_id, ".ondevice"),
            byte_size=0,
            uploaded_at=self._clock.now(),
            demo=self._demo,
        )
        return await self._ingest_extraction(
            extraction, hospital_id=hospital_id, intake_id=intake_id
        )

    async def _ingest_extraction(
        self, extraction: DocumentExtraction, *, hospital_id: str, intake_id: str
    ) -> DocumentExtraction:
        """The path both entry points share.

        Marks low-confidence numerics, classifies lab values against their own
        printed ranges, persists, turns medicines and diagnoses into
        document-channel facts, and emits.
        """
        now = self._clock.now()
        graded = _grade(extraction, floor=self._floor)

        await self._documents.save_extraction(
            graded, hospital_id=hospital_id, intake_id=intake_id, processed_at=now
        )

        if graded.was_rejected:
            await self._bus.publish(
                Event(
                    name=EventName.DOCUMENT_REJECTED,
                    occurred_at=now,
                    intake_id=intake_id,
                    document_id=graded.document_id,
                    payload={"reason": graded.quality_reason or "unreadable"},
                )
            )
            return graded

        facts = self._facts_from(graded, now=now)
        await self._intakes.append_facts(
            hospital_id=hospital_id, intake_id=intake_id, facts=facts
        )

        await self._bus.publish(
            Event(
                name=EventName.DOCUMENT_PROCESSED,
                occurred_at=now,
                intake_id=intake_id,
                document_id=graded.document_id,
                payload={
                    "kind": graded.kind.value,
                    "item_count": len(graded.items),
                    "low_confidence": graded.low_confidence,
                    "redaction_count": sum(graded.redactions.values()),
                },
            )
        )
        if graded.low_confidence:
            await self._bus.publish(
                Event(
                    name=EventName.DOCUMENT_LOW_CONFIDENCE,
                    occurred_at=now,
                    intake_id=intake_id,
                    document_id=graded.document_id,
                    payload={
                        "count": sum(1 for i in graded.items if i.needs_verification)
                    },
                )
            )
        return graded

    def _facts_from(self, extraction: DocumentExtraction, *, now: datetime) -> list[Fact]:
        """Document items as facts on the document channel.

        They enter the record beside — never over — what the patient said. The
        contradiction detector reads both, which is only possible because these
        are a separate channel rather than a correction of the voice facts.
        """
        facts: list[Fact] = []
        for item in extraction.items:
            field_id, value, section = _fact_shape(item, self._ingredients)
            if field_id is None:
                continue
            facts.append(
                Fact(
                    fact_id=f"fact_{item.item_id}",
                    field_id=field_id,
                    status=FieldStatus.ANSWERED,
                    value=value,
                    original_text=item.raw_text,
                    language=None,
                    source=DocumentSource(
                        kind="document",
                        document_id=extraction.document_id,
                        page=item.page,
                        bbox=item.bbox,
                    ),
                    confidence=item.confidence,
                    # A document is not a person speaking. Nothing read off a
                    # scan is better than REPORTED, and a low-confidence read is
                    # weaker still.
                    certainty=(
                        Certainty.UNCERTAIN if item.needs_verification else Certainty.REPORTED
                    ),
                    section=section,
                    channel=FactChannel.DOCUMENT,
                    needs_verification=item.needs_verification,
                    recorded_at=now,
                    note=f"document={extraction.document_id}",
                )
            )
        return facts

    # --- interactions -------------------------------------------------------

    def interactions_for(
        self, *, voice_medicines: Sequence[str], extractions: Sequence[DocumentExtraction]
    ) -> tuple[InteractionFinding, ...]:
        """Sourced interaction pairs among everything the patient is taking.

        Drug–drug only, among medicines already being taken. A name that does
        not resolve to an ingredient contributes nothing — see
        `app.domain.documents.interactions`.
        """
        from app.domain.documents.interactions import check

        entries: list[MedicineEntry] = []
        for name in voice_medicines:
            key = self._ingredients.resolve(name)
            if key:
                entries.append(MedicineEntry(display=name, ingredient_key=key))
        for extraction in extractions:
            for item in extraction.medicines():
                assert item.medicine is not None
                key = item.medicine.ingredient_key or self._ingredients.resolve(
                    item.medicine.name
                )
                if key:
                    entries.append(
                        MedicineEntry(display=item.medicine.name, ingredient_key=key)
                    )
        return check(entries, self._interactions)


# --- grading -----------------------------------------------------------------


def _grade(extraction: DocumentExtraction, *, floor: float) -> DocumentExtraction:
    """Mark low-confidence numerics and classify lab values.

    §6.5: any numeric value in a dose or a lab result below the floor is
    `needs_verification`. The benchmark read ९००.२ for १००.२ — one digit — and a
    wrong digit in a dose is the most dangerous error this system can make.
    """
    if extraction.quality is QualityVerdict.REJECTED:
        return extraction

    graded: list[DocumentItem] = []
    for item in extraction.items:
        carries_number = (
            item.medicine is not None and item.medicine.dose_magnitude is not None
        ) or (item.lab_result is not None and item.lab_result.value is not None)
        needs_verification = item.needs_verification or (
            carries_number and item.confidence < floor
        )
        range_status = item.range_status
        if item.lab_result is not None:
            range_status = classify(item.lab_result, needs_verification=needs_verification)
        graded.append(
            item.model_copy(
                update={
                    "needs_verification": needs_verification,
                    "range_status": range_status,
                }
            )
        )
    return extraction.model_copy(update={"items": graded})


def _fact_shape(
    item: DocumentItem, ingredients: IngredientIndex
) -> tuple[str | None, Coded | Quantity | Text | None, Section]:
    """The field id, value and section for one document item."""
    if item.medicine is not None:
        key = item.medicine.ingredient_key or ingredients.resolve(item.medicine.name)
        # An unresolved medicine still becomes a fact — it is printed on the
        # report and shown to the physician. It simply cannot participate in an
        # interaction check, because we do not know what it is.
        field_id = f"medication_{key}" if key else "current_medications"
        return field_id, Text(text=item.medicine.render()), Section.MEDICATIONS
    if item.lab_result is not None:
        analyte = item.lab_result.analyte.strip().lower().replace(" ", "_")
        if item.lab_result.value is not None and item.lab_result.unit:
            value: Coded | Quantity | Text = Quantity(
                magnitude=item.lab_result.value, unit=item.lab_result.unit
            )
        else:
            value = Text(text=item.lab_result.render())
        return f"lab_{analyte}", value, Section.INVESTIGATIONS
    if item.kind is ItemKind.DIAGNOSIS and item.label:
        slug = item.label.strip().lower().replace(" ", "_")
        return (
            f"condition_{slug}",
            Coded(code=slug, display=item.label),
            Section.PAST_MEDICAL,
        )
    if item.kind is ItemKind.PROCEDURE and item.label:
        slug = item.label.strip().lower().replace(" ", "_")
        return (
            f"surgery_{slug}",
            Coded(code=slug, display=item.label),
            Section.PAST_SURGICAL,
        )
    return None, None, Section.INVESTIGATIONS


def storage_suffix(key: str) -> str:
    return PurePosixPath(key).suffix
