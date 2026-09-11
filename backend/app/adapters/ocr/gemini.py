"""Vertex AI OCR provider.

**Read `docs/DECISIONS.md` before enabling this.** §6.2 of the implementation
brief makes three things a precondition, and this module refuses to construct
unless they are configured:

1. the model is served from an Indian region (`VERTEX_REGION`),
2. ML *processing* — not merely storage at rest — stays in that region,
3. Zero Data Retention is enabled (`VERTEX_ZDR_ENABLED`).

Point 2 is the one that is easy to get wrong. A "data residency" guarantee that
covers storage but routes inference elsewhere is not residency for this purpose:
the prescription is the payload, and it is the payload that has to stay in the
country. The residency findings recorded in `docs/DECISIONS.md` were verified
against Google's published Vertex AI data-residency terms, and that document
says exactly what was and was not confirmed.

The model id is never inline. `OCR_MODEL_ID` is read from settings, which is
what makes swapping a model a deployment change.

This adapter is excluded from coverage. It is exercised by hand against a real
project, never in CI, and the mock is what the test suite runs.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import MediKioskError
from app.core.logging import get_logger
from app.domain.documents.extraction import DocumentExtraction, QualityVerdict
from app.domain.documents.redaction import redact
from app.domain.record import DocumentKind

logger = get_logger(__name__)

#: The extraction contract handed to the model. It asks for structure and
#: nothing else: no interpretation, no normalisation of drug names, no filling
#: in of a reference range that was not printed.
EXTRACTION_INSTRUCTION = """\
You are reading a photographed medical document from an Indian hospital OPD.

Transcribe what is printed or written. Return JSON matching the provided schema.

Rules, all of them absolute:
- Transcribe only. Never infer, complete or correct a value that is not legible.
- If a character is unclear, lower the confidence for that item. Do not guess.
- Reference ranges: record ONLY a range printed on this document. If none is
  printed, omit the field. Never supply a range from your own knowledge.
- Do not interpret results. Do not state whether a value is normal or abnormal.
- Do not add a diagnosis, an impression or any advice.
- Give every item a page number, a bounding box in normalised 0..1 coordinates,
  a confidence in 0..1, and the raw text exactly as it appears.
- document_date: ISO 8601 only, YYYY-MM-DD. A date printed 04/09/2026 on an
  Indian document is 4 September 2026; write it 2026-09-04. If the printed date
  is ambiguous, undated or unclear, omit the field entirely. Never guess a date.
- Create an item only for content that matters clinically: a medicine, a
  diagnosis, a procedure, an investigation or lab result, or free text that
  carries clinical meaning (a symptom, an examination finding, an instruction
  or advice from the practitioner). Do not create an item for a form's own
  furniture: letterhead, clinic name or address, the doctor's name,
  registration or licence number, a signature or stamp line, a printed field
  label with no clinical content, a patient demographic line (name, age, sex,
  father's or guardian's name, home address, an ID number), a date that is only
  the form's own issue, print or signature date, or a serial or reference
  number. If genuinely unsure whether a line is clinical, keep it — but do not
  manufacture an item out of a form's own boilerplate.
"""


class ProviderNotConfigured(MediKioskError):
    """The Vertex provider was selected without the configuration it requires."""

    status_code = 500
    code = "ocr_provider_not_configured"


class GeminiOCRProvider:
    """Vertex AI multimodal OCR.

    Constructing this without residency and ZDR configured raises. That is
    deliberate: the failure mode worth preventing is a demo that quietly ships a
    patient's prescription to another jurisdiction because someone set
    `OCR_PROVIDER=gemini` and nothing complained.
    """

    name = "gemini"

    #: Regions where Vertex serves models inside India.
    INDIAN_REGIONS: frozenset[str] = frozenset({"asia-south1", "asia-south2"})

    def __init__(self, settings: Settings) -> None:
        if not settings.ocr_model_id:
            raise ProviderNotConfigured(
                "OCR_MODEL_ID is not set; the model is configuration, never a literal"
            )
        if not settings.vertex_project:
            raise ProviderNotConfigured("VERTEX_PROJECT is not set")
        if settings.vertex_region not in self.INDIAN_REGIONS:
            raise ProviderNotConfigured(
                f"VERTEX_REGION is '{settings.vertex_region}', which is not an Indian "
                f"region. Serving this model from outside India is a decision for the "
                f"team, not for the service — see docs/DECISIONS.md. "
                f"Indian regions: {sorted(self.INDIAN_REGIONS)}"
            )
        if not settings.vertex_zdr_enabled:
            raise ProviderNotConfigured(
                "VERTEX_ZDR_ENABLED is false. Zero Data Retention must be confirmed on "
                "the project before a patient's prescription is sent to a model."
            )
        self._settings = settings
        self._model_id = settings.ocr_model_id
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover
                raise ProviderNotConfigured(
                    "google-genai is not installed; install the 'gcp' extra"
                ) from exc
            self._client = genai.Client(
                vertexai=True,
                project=self._settings.vertex_project,
                location=self._settings.vertex_region,
            )
        return self._client

    async def read(
        self, image: bytes, *, document_id: str, hint: DocumentKind | None = None
    ) -> DocumentExtraction:
        from google.genai import types

        client = self._get_client()
        response = await client.aio.models.generate_content(
            model=self._model_id,
            contents=[
                types.Part.from_bytes(data=image, mime_type="image/jpeg"),
                EXTRACTION_INSTRUCTION,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_response_schema(),
                temperature=0.0,
            ),
        )

        try:
            body: dict[str, Any] = json.loads(response.text)
        except (ValueError, AttributeError):
            logger.warning("ocr_response_unparseable", document_id=document_id)
            return DocumentExtraction(
                document_id=document_id,
                kind=hint or DocumentKind.OTHER,
                quality=QualityVerdict.REJECTED,
                quality_reason="provider returned an unreadable response",
                provider=self.name,
                model_id=self._model_id,
            )

        return _to_extraction(
            body, document_id=document_id, hint=hint, model_id=self._model_id
        )


def _to_extraction(
    body: dict[str, Any],
    *,
    document_id: str,
    hint: DocumentKind | None,
    model_id: str,
) -> DocumentExtraction:
    """Validate the provider's JSON and redact it on the way in.

    Redaction happens here, at the boundary, before anything is persisted or
    logged. The benchmark corpus produced exactly one Aadhaar leak this way and
    it will produce another.
    """
    body = dict(body)
    body["document_id"] = document_id
    body.setdefault("kind", (hint or DocumentKind.OTHER).value)
    body["provider"] = "gemini"
    body["model_id"] = model_id

    counts: dict[str, int] = {}
    body["page_text"] = []
    for page in body.get("pages", []) or []:
        result = redact(str(page))
        body["page_text"].append(result.text)
        for label, count in result.counts:
            counts[label] = counts.get(label, 0) + count
    body.pop("pages", None)

    items = []
    for item in body.get("items", []) or []:
        entry = dict(item)
        result = redact(str(entry.get("raw_text", "")))
        entry["raw_text"] = result.text
        for label, count in result.counts:
            counts[label] = counts.get(label, 0) + count
        items.append(entry)
    body["items"] = items
    body["redactions"] = counts
    _drop_unparseable_date(body, document_id=document_id)

    try:
        return DocumentExtraction.model_validate(body)
    except ValidationError:
        # The model answered, and what it answered does not fit the contract.
        #
        # This has to be a verdict rather than an exception. The caller has
        # already marked the row `processing`, and in the cloud it is a Pub/Sub
        # push: raising here leaves the document stuck, 500s the push, and burns
        # all five delivery attempts before dead-lettering something a person
        # could have looked at immediately. A rejected document is visible. A
        # stuck one is not.
        #
        # No `exc_info`, and no field names: a pydantic error message quotes the
        # offending input, and the offending input is the document (§1 rule 7).
        logger.warning("ocr_response_off_contract", document_id=document_id)
        return DocumentExtraction(
            document_id=document_id,
            kind=hint or DocumentKind.OTHER,
            quality=QualityVerdict.REJECTED,
            quality_reason="provider returned a response that failed validation",
            provider="gemini",
            model_id=model_id,
        )


def _drop_unparseable_date(body: dict[str, Any], *, document_id: str) -> None:
    """Keep `document_date` only when it is unambiguously ISO 8601.

    The first live call against Vertex returned `"04/09/2026"` — the date as
    printed, which is what "transcribe only" asks for everywhere else in this
    contract, and which pydantic rejects. The instruction and the schema now
    both say ISO; this is what happens when the model does it anyway.

    Dropping it is the only correct answer. `04/09/2026` is 4 September to an
    Indian clerk and 9 April to an American parser, and this codebase does not
    resolve an ambiguity on a patient's behalf — repair does not, the walker
    does not, and neither does this. The date is still in `page_text` exactly as
    printed, so nothing is lost that a physician cannot read; what is lost is a
    structured date nobody could have trusted.
    """
    value = body.get("document_date")
    if value in (None, ""):
        body.pop("document_date", None)
        return
    try:
        date.fromisoformat(str(value))
    except (TypeError, ValueError):
        logger.info("ocr_document_date_not_iso", document_id=document_id)
        body.pop("document_date", None)


def _response_schema() -> dict[str, Any]:
    """The JSON schema enforced on the model's output.

    Structured output with the schema enforced, rather than a prompt asking
    nicely: a free-text response would put parsing between us and a dose.
    """
    return {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["prescription", "lab_report", "discharge_summary", "other"],
            },
            "page_count": {"type": "integer"},
            "document_date": {
                "type": "string",
                "description": "ISO 8601 date, YYYY-MM-DD. Omit if not printed or ambiguous.",
            },
            "issuing_facility": {"type": "string"},
            "overall_confidence": {"type": "number"},
            "pages": {"type": "array", "items": {"type": "string"}},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": [
                                "medicine",
                                "diagnosis",
                                "lab_result",
                                "procedure",
                                "other",
                            ],
                        },
                        "raw_text": {"type": "string"},
                        "page": {"type": "integer"},
                        "confidence": {"type": "number"},
                        "bbox": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "width": {"type": "number"},
                                "height": {"type": "number"},
                            },
                            "required": ["x", "y", "width", "height"],
                        },
                        "label": {"type": "string"},
                        "medicine": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "dose_magnitude": {"type": "number"},
                                "dose_unit": {"type": "string"},
                                "frequency": {"type": "string"},
                                "duration": {"type": "string"},
                                "route": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                        "lab_result": {
                            "type": "object",
                            "properties": {
                                "analyte": {"type": "string"},
                                "value": {"type": "number"},
                                "unit": {"type": "string"},
                                "text_value": {"type": "string"},
                                "reference_range": {
                                    "type": "object",
                                    "properties": {
                                        "low": {"type": "number"},
                                        "high": {"type": "number"},
                                        "unit": {"type": "string"},
                                        "raw_text": {"type": "string"},
                                    },
                                },
                            },
                            "required": ["analyte"],
                        },
                    },
                    "required": ["item_id", "kind", "raw_text", "page", "confidence"],
                },
            },
        },
        "required": ["kind", "items"],
    }
