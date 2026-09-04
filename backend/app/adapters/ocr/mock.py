"""Deterministic OCR provider.

Used by every test and by demo mode. It reads a fixture keyed by a hash of the
image bytes, so the same photograph always produces the same extraction —
which is what makes the end-to-end test and the golden report files possible at
all.

It is not a simulation of OCR quality. It is a recording of it: the fixtures are
built from the thirteen-page benchmark corpus, including its failure modes, so
the low-confidence path and the digit-verification path are exercised by real
misreadings rather than invented ones.

An unknown image gets a deterministic, explicitly empty extraction rather than an
error. A demo with a photograph nobody prepared should show "not yet processed",
not a stack trace.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.domain.documents.extraction import (
    DocumentExtraction,
    QualityVerdict,
)
from app.domain.documents.redaction import redact
from app.domain.record import DocumentKind

logger = get_logger(__name__)

#: Images smaller than this are treated as failing the quality gate. A real
#: gate measures blur and skew; this one measures the only thing a fixture
#: provider honestly can, and keeps the reject path exercised.
MIN_PLAUSIBLE_BYTES = 64


def fixture_key(data: bytes) -> str:
    """The fixture name for these bytes. Stable across runs and machines."""
    return hashlib.sha256(data).hexdigest()[:16]


class MockOCRProvider:
    """Fixture-backed OCR."""

    name = "mock"

    def __init__(self, fixtures_dir: Path, *, demo: bool = False) -> None:
        self._dir = fixtures_dir
        self._demo = demo

    async def read(
        self, image: bytes, *, document_id: str, hint: DocumentKind | None = None
    ) -> DocumentExtraction:
        if len(image) < MIN_PLAUSIBLE_BYTES:
            return DocumentExtraction(
                document_id=document_id,
                kind=hint or DocumentKind.OTHER,
                quality=QualityVerdict.REJECTED,
                quality_reason="image too small to read",
                provider=self.name,
                demo=self._demo,
            )

        raw = self._load(fixture_key(image))
        if raw is None:
            logger.info("ocr_fixture_missing", document_id=document_id, provider=self.name)
            return DocumentExtraction(
                document_id=document_id,
                kind=hint or DocumentKind.OTHER,
                quality=QualityVerdict.ACCEPTED,
                provider=self.name,
                demo=self._demo,
            )

        return _extraction_from_fixture(
            raw, document_id=document_id, hint=hint, provider=self.name, demo=self._demo
        )

    def _load(self, key: str) -> dict[str, Any] | None:
        path = self._dir / f"{key}.json"
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as handle:
            loaded: dict[str, Any] = json.load(handle)
        return loaded


def _extraction_from_fixture(
    raw: dict[str, Any],
    *,
    document_id: str,
    hint: DocumentKind | None,
    provider: str,
    demo: bool,
) -> DocumentExtraction:
    """Build an extraction from a fixture, redacting on the way through.

    The redaction pass runs here rather than in the service, so that even a
    fixture author who pastes an Aadhaar number into a test file cannot get it
    into a database row.
    """
    # Fixture files carry `_fixture_name` so a failing test names the file it
    # came from. Underscore-prefixed keys are annotation, not payload.
    body = {k: v for k, v in raw.items() if not k.startswith("_")}
    body["document_id"] = document_id
    body.setdefault("kind", (hint or DocumentKind.OTHER).value)
    body["provider"] = provider
    body["demo"] = demo

    counts: dict[str, int] = {}
    pages: list[str] = []
    for page in body.get("page_text", []):
        result = redact(str(page))
        pages.append(result.text)
        for label, count in result.counts:
            counts[label] = counts.get(label, 0) + count
    body["page_text"] = pages

    items: list[dict[str, Any]] = []
    for item in body.get("items", []):
        entry = dict(item)
        result = redact(str(entry.get("raw_text", "")))
        entry["raw_text"] = result.text
        for label, count in result.counts:
            counts[label] = counts.get(label, 0) + count
        items.append(entry)
    body["items"] = items
    body["redactions"] = counts

    return DocumentExtraction.model_validate(body)
