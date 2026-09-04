"""Redaction — §13.10.

**An Aadhaar-shaped number in OCR text never reaches the database or a log.**

This is not a hypothetical. The benchmark corpus contained a legible Aadhaar
number on a prescription header, and a model transcribed it straight into its
result JSON. The `contains_aadhaar` fixture is that document's shape, and this
file is the test that stops it happening again.

Three layers, each tested:

1. The pattern matcher itself.
2. The OCR adapter, which redacts before returning.
3. The repository, which refuses to write anything identifier-shaped even if the
   first two were bypassed.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.domain.documents.redaction import contains_identifier, redact
from tests.conftest import HOSPITAL_ID


class TestThePatterns:
    @pytest.mark.parametrize(
        "text",
        [
            "Aadhaar 2345 6789 0123",
            "UID: 234567890123",
            "2345-6789-0123",
            "आधार २३४५ ६७८९ ०१२३",
            "Mobile 9876543210",
            "Ph +91 98765 43210",
            "09876543210",
            "ABHA 12345678901234",
            "PAN ABCDE1234F",
            "patient@example.com",
        ],
    )
    def test_identifiers_are_masked(self, text: str) -> None:
        result = redact(text)
        assert result.redacted_anything
        assert not contains_identifier(result.text)

    @pytest.mark.parametrize(
        "text",
        [
            "Tab. Metformin 500 mg BD",
            "Haemoglobin 9.8 g/dL (12.0 - 15.0 g/dL)",
            "Fasting glucose 148 mg/dL",
            "BP 120/80 mmHg",
            "Date: 14/08/2026",
            "पेट में दर्द तीन दिन से",
            "OPD 4521",
        ],
    )
    def test_clinical_text_is_untouched(self, text: str) -> None:
        """The counter-test.

        A redactor that eats doses and lab values is a redactor somebody turns
        off. `500 mg`, `12.0 - 15.0` and a four-digit OPD number all survive.
        """
        result = redact(text)
        assert result.text == text
        assert not result.redacted_anything

    def test_counts_are_reported_by_kind(self) -> None:
        """Counts are safe to log and worth logging.

        "This document produced four Aadhaar hits" is a document worth looking
        at, and the count says so without saying what the number was.
        """
        result = redact("Aadhaar 2345 6789 0123 and mobile 9876543210")
        assert dict(result.counts) == {"aadhaar": 1, "phone": 1}
        assert result.total == 2

    def test_redaction_is_idempotent(self) -> None:
        once = redact("Aadhaar 2345 6789 0123").text
        assert redact(once).text == once


class TestTheAdapterRedacts:
    async def test_the_leaking_fixture_comes_back_clean(
        self, providers: Any, ocr_images: dict[str, bytes]
    ) -> None:
        """The exact failure the benchmark produced, caught at the adapter."""
        extraction = await providers.ocr.read(
            ocr_images["contains_aadhaar"], document_id="doc_test"
        )
        assert extraction.redactions == {"aadhaar": 2, "phone": 2}
        for page in extraction.page_text:
            assert not contains_identifier(page)
        for item in extraction.items:
            assert not contains_identifier(item.raw_text)

    async def test_the_clinical_content_of_that_fixture_survives(
        self, providers: Any, ocr_images: dict[str, bytes]
    ) -> None:
        """Redaction removes the identifier, not the prescription.

        The document still yields its medicine. Masking the whole page would be
        safe and useless.
        """
        extraction = await providers.ocr.read(
            ocr_images["contains_aadhaar"], document_id="doc_test"
        )
        medicines = extraction.medicines()
        assert len(medicines) == 1
        assert medicines[0].medicine is not None
        assert medicines[0].medicine.name == "Metformin"


class TestNothingLeakedReachesTheDatabase:
    async def test_the_full_pipeline_stores_nothing_identifier_shaped(
        self,
        session: Any,
        ingest_service: Any,
        document_service: Any,
        kiosk_payload: dict[str, Any],
        ocr_images: dict[str, bytes],
    ) -> None:
        """Ingest, upload, process — then read every stored string back."""
        from sqlalchemy import select

        from app.models.clinical import DocumentItemRecord, DocumentRecordRow

        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        upload = await document_service.upload(
            hospital_id=HOSPITAL_ID,
            intake_id=result.intake_id,
            content=ocr_images["contains_aadhaar"],
            content_type="image/jpeg",
        )
        await document_service.process(
            hospital_id=HOSPITAL_ID, document_id=upload.document_id
        )

        documents = (
            await session.execute(
                select(DocumentRecordRow).where(
                    DocumentRecordRow.hospital_id == HOSPITAL_ID
                )
            )
        ).scalars().all()
        items = (
            await session.execute(
                select(DocumentItemRecord).where(
                    DocumentItemRecord.hospital_id == HOSPITAL_ID
                )
            )
        ).scalars().all()

        assert documents and items
        for row in documents:
            for page in row.page_text:
                assert not contains_identifier(page)
        for item in items:
            assert not contains_identifier(item.raw_text)
            assert not contains_identifier(json.dumps(item.payload or {}))

        # And the counts were kept, because they are the operational signal.
        assert documents[0].redactions == {"aadhaar": 2, "phone": 2}

    async def test_the_repository_refuses_an_unredacted_extraction(
        self, session: Any, ingest_service: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """The backstop, tested by bypassing the adapter.

        Even handed an extraction that skipped redaction — an on-device result
        from a build with the pass missing, say — the write is refused rather
        than performed and logged.
        """
        from app.domain.documents.extraction import DocumentExtraction, DocumentItem
        from app.domain.record import DocumentKind
        from app.repositories.documents import DocumentRepository, RedactionEscape

        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        repository = DocumentRepository(session)
        await repository.create(
            document_id="doc_raw",
            hospital_id=HOSPITAL_ID,
            intake_id=result.intake_id,
            kind=DocumentKind.PRESCRIPTION,
            content_type="image/jpeg",
            storage_key=f"{HOSPITAL_ID}/x/doc_raw.jpg",
            byte_size=1,
            uploaded_at=__import__("datetime").datetime.now(
                __import__("datetime").UTC
            ),
        )
        leaking = DocumentExtraction(
            document_id="doc_raw",
            kind=DocumentKind.PRESCRIPTION,
            items=[
                DocumentItem(
                    item_id="item_leak",
                    kind="other",
                    raw_text="Aadhaar 2345 6789 0123",
                    page=1,
                    confidence=0.9,
                )
            ],
            page_text=["Aadhaar 2345 6789 0123"],
        )
        with pytest.raises(RedactionEscape) as caught:
            await repository.save_extraction(
                leaking,
                hospital_id=HOSPITAL_ID,
                intake_id=result.intake_id,
                processed_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC
                ),
            )
        # The error names locations, never values — it reaches a log.
        assert "item_leak" in str(caught.value.details["locations"])
        assert "2345" not in json.dumps(caught.value.to_payload())
