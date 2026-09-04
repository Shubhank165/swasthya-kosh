"""Provider protocols.

Every place a cloud model could later plug in is defined here as a Protocol, and
implemented in this build only by deterministic mocks. That is the point of the
whole exercise: when Vertex AI, Sarvam or an OCR service arrives, nothing above
the adapters package changes, and the offline path keeps working.

Note what is NOT a protocol. There is no `NextQuestionProvider`, no
`CompletenessJudge`, no `RedFlagClassifier`. Those decisions belong to the
deterministic engine, permanently.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.statemachine.engine import Step


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """One recognised span of speech."""

    segment_id: str
    text: str
    language: str
    start_ms: int
    end_ms: int
    confidence: float
    is_final: bool = True


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """A slice of PCM audio on its way to or from a provider."""

    data: bytes
    sample_rate_hz: int = 16_000
    sequence: int = 0


@dataclass(frozen=True, slots=True)
class DocumentPage:
    """One page of an uploaded document."""

    page: int
    text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class DocumentExtraction:
    """What an OCR provider read off a document.

    `facts` are candidates only. They enter the record as unverified,
    document-sourced facts with the bounding box that produced them, and they
    stay `physician_verified = False` until a physician acts.
    """

    document_id: str
    pages: tuple[DocumentPage, ...]
    facts: tuple[ClinicalFact, ...] = field(default_factory=tuple)
    overall_confidence: float = 0.0
    #: True when the provider itself is unsure. Surfaces on the report as an
    #: explicit "verify against the original" line rather than being hidden.
    low_confidence: bool = False
    document_kind: str = "other"


@dataclass(frozen=True, slots=True)
class EncounterRef:
    """An encounter owned by a hospital HMIS, in SHADOW mode."""

    encounter_id: str
    patient_id: str
    department_code: str
    token_number: str | None = None
    scheduled_at: str | None = None


class STTProvider(Protocol):
    """Speech to text."""

    async def transcribe_stream(
        self, audio: AsyncIterator[AudioChunk], *, language: str
    ) -> AsyncIterator[TranscriptSegment]: ...


class TTSProvider(Protocol):
    """Text to speech. Receives a question string the state machine authored."""

    async def synthesize_stream(
        self, text: str, *, language: str
    ) -> AsyncIterator[AudioChunk]: ...


class ClinicalExtractor(Protocol):
    """Turns an utterance into candidate facts.

    It is given the current state so it can attach facts to the concept that was
    actually asked. It may not choose what to ask next, and its output is
    candidate facts — never the record itself.
    """

    async def extract(
        self, utterance: TranscriptSegment, state: PatientIntakeState, *, step: Step | None = None
    ) -> Sequence[ClinicalFact]: ...


class QuestionRenderer(Protocol):
    """Turns a `Step` into the words a patient hears.

    A generative renderer may vary phrasing and register. It receives the step
    already chosen; it cannot change the concept, the order or the answer shape.
    """

    async def render(self, step: Step, *, language: str) -> str: ...


class OCRProvider(Protocol):
    """Reads an uploaded prescription or report."""

    async def process(
        self, document_id: str, content: bytes, *, content_type: str
    ) -> DocumentExtraction: ...


class HISAdapter(Protocol):
    """Hospital information system integration, used in SHADOW mode."""

    async def resolve_encounter(self, identifier: str) -> EncounterRef | None: ...

    async def push_intake_summary(self, intake_id: str, summary: dict[str, Any]) -> bool: ...

    async def subscribe_queue_events(self) -> AsyncIterator[dict[str, Any]]: ...


class FHIRMapper(Protocol):
    """Maps an intake to a FHIR R4 Bundle."""

    def to_bundle(self, state: PatientIntakeState) -> dict[str, Any]: ...


class ABDMAdapter(Protocol):
    """ABHA identity and consent linkage.

    ABHA is an identity and consent-linking mechanism, not a database of the
    patient's history, and it is never required for basic intake.
    """

    async def verify_abha(self, abha_address: str) -> dict[str, Any] | None: ...

    async def link_care_context(self, abha_address: str, intake_id: str) -> bool: ...
