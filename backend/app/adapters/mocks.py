"""Deterministic mock providers.

These are scriptable, not random. The same input produces the same output every
time, which is what lets the whole system run end to end in CI with no network
and lets the evaluation harness produce numbers anyone can reproduce.

`TemplateQuestionRenderer` is not a mock. It reads the prompt straight out of the
pathway YAML, and it is the offline production path: a kiosk in a district
hospital with no internet runs on it permanently.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.adapters.protocols import (
    AudioChunk,
    DocumentExtraction,
    DocumentPage,
    EncounterRef,
    TranscriptSegment,
)
from app.core.ids import IdFactory, SequentialIdFactory
from app.domain.clinical.enums import (
    Certainty,
    FactStatus,
    ReporterRole,
    Section,
    SourceType,
    Temporality,
)
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import (
    BoundingBox,
    CodedValue,
    ConceptRef,
    DocumentId,
    FactId,
    SegmentId,
    SourceRef,
    TextValue,
)
from app.domain.ontology.concepts import ConceptRegistry
from app.domain.statemachine.engine import Step


class MockSTTProvider:
    """Replays a scripted list of segments. Nothing is recognised; nothing is
    guessed. Feeding it silence yields nothing rather than an invented answer."""

    def __init__(self, script: Sequence[TranscriptSegment] = ()) -> None:
        self._script = list(script)

    def load(self, script: Sequence[TranscriptSegment]) -> None:
        self._script = list(script)

    async def transcribe_stream(
        self, audio: AsyncIterator[AudioChunk], *, language: str
    ) -> AsyncIterator[TranscriptSegment]:
        # Drain the input so a caller streaming real chunks behaves the same as
        # one that does not, then replay the script.
        async for _ in audio:
            pass
        for segment in self._script:
            yield segment


class MockTTSProvider:
    """Emits a deterministic byte pattern sized from the text. Useful for
    asserting the pipeline moved audio without shipping an audio fixture."""

    def __init__(self, sample_rate_hz: int = 16_000) -> None:
        self._sample_rate_hz = sample_rate_hz

    async def synthesize_stream(
        self, text: str, *, language: str
    ) -> AsyncIterator[AudioChunk]:
        payload = f"{language}:{text}".encode()
        for index in range(0, len(payload), 32):
            yield AudioChunk(
                data=payload[index : index + 32],
                sample_rate_hz=self._sample_rate_hz,
                sequence=index // 32,
            )


class TemplateQuestionRenderer:
    """Returns the pathway's own prompt text, unchanged.

    A real implementation, not a stub. It is the fallback whenever a generative
    renderer is unavailable, and the only renderer a fully offline kiosk has.
    """

    async def render(self, step: Step, *, language: str) -> str:
        return step.prompts.get(language) or step.prompts.get("en") or step.question


class ScriptedExtractor:
    """Maps an utterance to facts by exact scripted lookup.

    Deliberately incapable of inference. If the script has no entry for an
    utterance it returns nothing, and the state machine asks again — which is
    the correct behaviour for a system that must never invent an answer.
    """

    def __init__(
        self,
        concepts: ConceptRegistry,
        *,
        id_factory: IdFactory | None = None,
        script: Mapping[str, Sequence[tuple[str, FactStatus, str | None]]] | None = None,
    ) -> None:
        self._concepts = concepts
        self._ids = id_factory or SequentialIdFactory()
        #: utterance text -> [(concept_id, status, coded value)]
        self._script: dict[str, list[tuple[str, FactStatus, str | None]]] = {
            key: list(value) for key, value in (script or {}).items()
        }

    def teach(
        self, utterance: str, facts: Sequence[tuple[str, FactStatus, str | None]]
    ) -> None:
        self._script[utterance] = list(facts)

    async def extract(
        self,
        utterance: TranscriptSegment,
        state: PatientIntakeState,
        *,
        step: Step | None = None,
    ) -> Sequence[ClinicalFact]:
        entries = self._script.get(utterance.text)
        if entries is None:
            return ()
        out: list[ClinicalFact] = []
        for concept_id, status, coded in entries:
            concept = self._concepts.get(concept_id)
            ref = concept.ref() if concept else ConceptRef(concept_id)
            section = concept.section if concept else Section.HPI
            out.append(
                ClinicalFact(
                    fact_id=FactId(self._ids.new_id("fact")),
                    concept=ref,
                    status=status,
                    # An extractor never produces CONFIRMED. Only the patient
                    # confirmation loop can raise certainty that far.
                    certainty=Certainty.REPORTED,
                    temporality=Temporality.CURRENT,
                    source_type=SourceType.VOICE,
                    source_ref=SourceRef.from_transcript(
                        SegmentId(utterance.segment_id), utterance.start_ms, utterance.end_ms
                    ),
                    confidence=utterance.confidence,
                    reported_by=state.reporter,
                    recorded_at=datetime.now(UTC),
                    section=section,
                    value=CodedValue(code=coded) if coded is not None else None,
                    # The verbatim words survive normalisation, always.
                    original_expression=utterance.text,
                    original_language=utterance.language,
                )
            )
        return out


class MockOCRProvider:
    """Returns scripted extractions keyed by document id.

    Facts it produces are DOCUMENT-sourced with a bounding box, so the physician
    report can link a line back to the region of the scan it came from.
    """

    def __init__(
        self,
        concepts: ConceptRegistry,
        *,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._concepts = concepts
        self._ids = id_factory or SequentialIdFactory()
        self._script: dict[str, list[tuple[str, FactStatus, str | None, float]]] = {}
        self._kinds: dict[str, str] = {}

    def teach(
        self,
        document_id: str,
        facts: Sequence[tuple[str, FactStatus, str | None, float]],
        *,
        kind: str = "discharge_summary",
    ) -> None:
        self._script[document_id] = list(facts)
        self._kinds[document_id] = kind

    async def process(
        self, document_id: str, content: bytes, *, content_type: str
    ) -> DocumentExtraction:
        entries = self._script.get(document_id, [])
        now = datetime.now(UTC)
        facts: list[ClinicalFact] = []
        for index, (concept_id, status, text, confidence) in enumerate(entries):
            concept = self._concepts.get(concept_id)
            ref = concept.ref() if concept else ConceptRef(concept_id)
            section = concept.section if concept else Section.DOCUMENTS
            facts.append(
                ClinicalFact(
                    fact_id=FactId(self._ids.new_id("fact")),
                    concept=ref,
                    status=status,
                    certainty=Certainty.REPORTED,
                    # A document describes the past unless it says otherwise.
                    temporality=Temporality.HISTORICAL,
                    source_type=SourceType.DOCUMENT,
                    source_ref=SourceRef.from_document(
                        DocumentId(document_id),
                        page=1,
                        bbox=BoundingBox(x=0.1, y=0.1 + 0.08 * index, width=0.6, height=0.05),
                    ),
                    confidence=confidence,
                    reported_by=ReporterRole.STAFF,
                    recorded_at=now,
                    section=section,
                    value=TextValue(text) if text is not None else None,
                    # Nothing a machine read off a scan is verified.
                    physician_verified=False,
                )
            )
        confidences = [c for _, _, _, c in entries]
        overall = min(confidences) if confidences else 0.0
        return DocumentExtraction(
            document_id=document_id,
            pages=(DocumentPage(page=1, text="", confidence=overall),),
            facts=tuple(facts),
            overall_confidence=overall,
            low_confidence=bool(confidences) and overall < 0.7,
            document_kind=self._kinds.get(document_id, "other"),
        )


class MockHISAdapter:
    """Stands in for a hospital HMIS in SHADOW mode."""

    def __init__(self) -> None:
        self._encounters: dict[str, EncounterRef] = {}
        self._pushed: list[tuple[str, dict[str, Any]]] = []
        self._queue_events: list[dict[str, Any]] = []

    def register(self, encounter: EncounterRef) -> None:
        self._encounters[encounter.encounter_id] = encounter
        self._encounters[encounter.patient_id] = encounter

    async def resolve_encounter(self, identifier: str) -> EncounterRef | None:
        return self._encounters.get(identifier)

    async def push_intake_summary(self, intake_id: str, summary: dict[str, Any]) -> bool:
        self._pushed.append((intake_id, summary))
        return True

    async def subscribe_queue_events(self) -> AsyncIterator[dict[str, Any]]:
        for event in list(self._queue_events):
            yield event

    def enqueue_event(self, event: dict[str, Any]) -> None:
        self._queue_events.append(event)

    @property
    def pushed(self) -> tuple[tuple[str, dict[str, Any]], ...]:
        return tuple(self._pushed)


class MockABDMAdapter:
    """ABHA verification stand-in.

    Returns identity only, never history: treating ABHA as a record store is a
    category error the build brief calls out explicitly.
    """

    def __init__(self) -> None:
        self._known: dict[str, dict[str, Any]] = {}
        self._links: list[tuple[str, str]] = []

    def register(self, abha_address: str, profile: dict[str, Any]) -> None:
        self._known[abha_address] = profile

    async def verify_abha(self, abha_address: str) -> dict[str, Any] | None:
        return self._known.get(abha_address)

    async def link_care_context(self, abha_address: str, intake_id: str) -> bool:
        if abha_address not in self._known:
            return False
        self._links.append((abha_address, intake_id))
        return True

    @property
    def links(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._links)
