"""Turning a submitted answer into facts.

This is where the "never silently increase certainty" invariant is actually
enforced, because this is the only place a raw answer becomes a `ClinicalFact`.

Three rules govern everything here:
  - a "don't know" answer produces `UNKNOWN`, never absence,
  - a hedged answer produces `APPROXIMATE`, and nothing downstream may promote it,
  - the patient's verbatim words are attached to every fact built from them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.core.errors import ValidationError
from app.domain.clinical.enums import (
    AnswerShape,
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
    BooleanValue,
    CodedValue,
    ConceptRef,
    DateValue,
    Duration,
    FactId,
    FactValue,
    Quantity,
    ScaleValue,
    SegmentId,
    SourceRef,
    TextValue,
)
from app.domain.ontology.concepts import ConceptRegistry
from app.domain.statemachine.engine import Step

#: Tokens that mean "I don't know". They map to UNKNOWN — never to ABSENT, and
#: never to a missing fact. "I don't know if I'm diabetic" is clinically
#: different from "I am not diabetic", and the record must show which was said.
UNKNOWN_TOKENS: frozenset[str] = frozenset(
    {
        "unknown",
        "not_sure",
        "not sure",
        "dont_know",
        "don't know",
        "dont know",
        "पता नहीं",
        "मालूम नहीं",
        "prefer_not_to_say",
    }
)

#: Affirmative and negative tokens for yes/no/unknown and confirmation shapes.
YES_TOKENS: frozenset[str] = frozenset({"yes", "true", "present", "correct", "हाँ", "हां", "ha"})
NO_TOKENS: frozenset[str] = frozenset({"no", "false", "absent", "नहीं", "nahi", "nahin"})

#: Tokens that mean "I would rather not answer". Distinct from UNKNOWN: the
#: patient knows, and has declined. Both are distinct from never being asked.
DECLINE_TOKENS: frozenset[str] = frozenset({"skip", "decline", "prefer_not_to_answer", "pass"})

#: Hedging words. Their presence caps certainty at APPROXIMATE, which is how
#: "maybe two weeks" is stopped from becoming "2 weeks" at the boundary.
HEDGE_TOKENS: tuple[str, ...] = (
    "maybe",
    "about",
    "around",
    "roughly",
    "approximately",
    "some",
    "shayad",
    "lagbhag",
    "करीब",
    "शायद",
    "लगभग",
    "थोड़ा",
)

#: Duration units the parser accepts, including the Hindi words a patient uses.
_DURATION_UNITS: Mapping[str, str] = {
    "hour": "hours", "hours": "hours", "hr": "hours", "ghanta": "hours", "घंटे": "hours",
    "day": "days", "days": "days", "din": "days", "दिन": "days",
    "week": "weeks", "weeks": "weeks", "hafta": "weeks", "hafte": "weeks", "हफ्ते": "weeks",
    "month": "months", "months": "months", "mahina": "months", "महीने": "months",
    "year": "years", "years": "years", "saal": "years", "साल": "years",
}


@dataclass(frozen=True, slots=True)
class SubmittedAnswer:
    """One answer as it arrives from the kiosk."""

    concept: str
    #: `None` means the patient gave no answer. It never becomes "no".
    value: Any | None = None
    #: The patient's own words, when the answer came by voice.
    original_expression: str | None = None
    original_language: str | None = None
    source_type: SourceType = SourceType.TOUCH
    reported_by: ReporterRole | None = None
    confidence: float = 1.0
    declined: bool = False
    #: Transcript provenance, when the answer came by voice.
    segment_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    #: Who entered it, when the answer came by touch or from staff.
    actor: str | None = None


def _is_unknown(raw: Any) -> bool:
    return isinstance(raw, str) and raw.strip().lower() in UNKNOWN_TOKENS


def _is_declined(raw: Any) -> bool:
    return isinstance(raw, str) and raw.strip().lower() in DECLINE_TOKENS


def _is_hedged(text: str | None) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(token in lowered for token in HEDGE_TOKENS)


def certainty_for(answer: SubmittedAnswer) -> Certainty:
    """Certainty of a submitted answer.

    Never CONFIRMED: only the patient confirmation loop can reach that, because
    only a human re-affirming what we recorded justifies it.
    """
    if _is_hedged(answer.original_expression):
        return Certainty.APPROXIMATE
    if answer.confidence < 0.6:
        return Certainty.UNCERTAIN
    return Certainty.REPORTED


def temporality_for(answer: SubmittedAnswer, section: Section) -> Temporality:
    if _is_hedged(answer.original_expression):
        return Temporality.APPROXIMATE
    if section in {Section.PAST_MEDICAL, Section.PAST_SURGICAL, Section.FAMILY_HISTORY}:
        return Temporality.HISTORICAL
    return Temporality.CURRENT


def parse_duration(raw: Any) -> Duration:
    """Parse `"2 weeks"`, `{"magnitude": 2, "unit": "weeks"}` or `"do hafte"`.

    Deliberately refuses rather than guesses. A duration it cannot parse is a
    question that gets asked again, which is always better than a number the
    patient never said.
    """
    if isinstance(raw, Mapping):
        magnitude = raw.get("magnitude")
        unit = str(raw.get("unit", "")).lower()
        if magnitude is None or unit not in _DURATION_UNITS.values():
            raise ValidationError(f"unparseable duration: {raw!r}")
        return Duration(float(magnitude), unit)
    if isinstance(raw, str):
        parts = raw.strip().lower().split()
        if len(parts) == 2:
            magnitude_text, unit_text = parts
            unit = _DURATION_UNITS.get(unit_text)
            if unit is not None:
                try:
                    return Duration(float(magnitude_text), unit)
                except ValueError as exc:
                    raise ValidationError(f"unparseable duration: {raw!r}") from exc
    raise ValidationError(f"unparseable duration: {raw!r}")


def _coerce(shape: AnswerShape, raw: Any, step: Step | None) -> FactValue | None:
    """Turn a raw answer into the typed value its shape demands."""
    if shape in {AnswerShape.YES_NO_UNKNOWN, AnswerShape.CONFIRMATION}:
        return None  # carried entirely by status
    if shape is AnswerShape.DURATION:
        return parse_duration(raw)
    if shape is AnswerShape.QUANTITY:
        unit = (step.answer.unit if step else None) or "unit"
        if isinstance(raw, Mapping):
            return Quantity(float(raw["magnitude"]), str(raw.get("unit", unit)))
        return Quantity(float(raw), unit)
    if shape is AnswerShape.SCALE:
        minimum = step.answer.minimum if step and step.answer.minimum is not None else 0.0
        maximum = step.answer.maximum if step and step.answer.maximum is not None else 10.0
        return ScaleValue(float(raw), minimum, maximum)
    if shape is AnswerShape.DATE:
        if isinstance(raw, Mapping):
            precision = str(raw.get("precision", "day"))
            return DateValue(date.fromisoformat(str(raw["value"])), precision)
        text = str(raw)
        if len(text) == 4 and text.isdigit():
            # "2019" is a year, and saying so is more honest than pinning it to
            # the 1st of January.
            return DateValue(date(int(text), 1, 1), precision="year")
        return DateValue(date.fromisoformat(text))
    if shape is AnswerShape.MULTI_CHOICE:
        if isinstance(raw, str):
            return CodedValue(code=raw)
        if isinstance(raw, Sequence):
            return CodedValue(code=",".join(str(item) for item in raw))
        raise ValidationError(f"multi-choice answer must be a list, got {type(raw).__name__}")
    if shape is AnswerShape.SINGLE_CHOICE:
        return CodedValue(code=str(raw))
    return TextValue(str(raw))


def _validate_choice(shape: AnswerShape, raw: Any, step: Step | None) -> None:
    """Reject a choice that is not on the step's option list.

    An option the content did not offer is a client bug, and accepting it would
    put a value in the record that no clinician ever authored.
    """
    if step is None or not step.answer.options:
        return
    allowed = set(step.answer.options) | UNKNOWN_TOKENS | DECLINE_TOKENS
    values = raw if isinstance(raw, list | tuple) else [raw]
    unknown = [str(v) for v in values if str(v) not in allowed]
    if unknown and shape in {AnswerShape.SINGLE_CHOICE, AnswerShape.MULTI_CHOICE}:
        raise ValidationError(
            f"answer {unknown} is not among the options offered for '{step.concept}'",
            details={"concept": step.concept, "options": list(step.answer.options)},
        )


def _source_ref(answer: SubmittedAnswer) -> SourceRef:
    if answer.segment_id is not None:
        return SourceRef.from_transcript(
            SegmentId(answer.segment_id), answer.start_ms or 0, answer.end_ms or 0
        )
    return SourceRef.from_actor(answer.actor or answer.source_type.value)


def build_fact(
    answer: SubmittedAnswer,
    state: PatientIntakeState,
    concepts: ConceptRegistry,
    *,
    fact_id: str,
    now: datetime,
    step: Step | None = None,
) -> ClinicalFact:
    """Build the fact for one submitted answer.

    The status decision is the whole point of this function:
      - declined, or a decline token -> the caller records a decline, not a fact,
      - an unknown token, or no value at all, -> `UNKNOWN`,
      - "no" on a yes/no question -> `ABSENT`,
      - anything else -> `PRESENT` with the coerced value.
    """
    concept = concepts.get(answer.concept)
    ref = concept.ref() if concept else ConceptRef(answer.concept)
    section = step.section if step else (concept.section if concept else Section.HPI)
    shape = step.answer.shape if step else AnswerShape.FREE_TEXT

    raw = answer.value
    status: FactStatus
    value: FactValue | None = None

    if raw is None or _is_unknown(raw):
        # No answer never becomes "no". This is invariant 4 at its sharpest.
        status = FactStatus.UNKNOWN
    elif shape in {AnswerShape.YES_NO_UNKNOWN, AnswerShape.CONFIRMATION}:
        token = str(raw).strip().lower()
        if token in YES_TOKENS:
            status = FactStatus.PRESENT
        elif token in NO_TOKENS:
            status = FactStatus.ABSENT
        else:
            status = FactStatus.UNKNOWN
    else:
        _validate_choice(shape, raw, step)
        status = FactStatus.PRESENT
        value = _coerce(shape, raw, step)

    return ClinicalFact(
        fact_id=FactId(fact_id),
        concept=ref,
        status=status,
        certainty=certainty_for(answer),
        temporality=temporality_for(answer, section),
        source_type=answer.source_type,
        source_ref=_source_ref(answer),
        confidence=answer.confidence,
        reported_by=answer.reported_by or state.reporter,
        recorded_at=now,
        section=section,
        value=value,
        # The verbatim expression rides along with the normalised concept,
        # always. Nothing in the pipeline is permitted to drop it.
        original_expression=answer.original_expression,
        original_language=answer.original_language or state.language,
    )


def is_decline(answer: SubmittedAnswer) -> bool:
    return answer.declined or _is_declined(answer.value)


def not_applicable_fact(
    concept_id: str,
    section: Section,
    concepts: ConceptRegistry,
    *,
    fact_id: str,
    now: datetime,
    reason: str,
) -> ClinicalFact:
    """A fact recording that a question was correctly never asked.

    `note` carries the failing precondition, so the record answers "why is there
    no pregnancy question here?" without anyone having to reconstruct it.
    """
    concept = concepts.get(concept_id)
    return ClinicalFact(
        fact_id=FactId(fact_id),
        concept=concept.ref() if concept else ConceptRef(concept_id),
        status=FactStatus.NOT_APPLICABLE,
        certainty=Certainty.CONFIRMED,
        temporality=Temporality.CURRENT,
        source_type=SourceType.DERIVED,
        source_ref=SourceRef.from_actor("state_machine"),
        confidence=1.0,
        reported_by=ReporterRole.STAFF,
        recorded_at=now,
        section=section,
        note=f"precondition not satisfied: {reason}",
    )


def boolean_value(flag: bool) -> BooleanValue:
    """Wrap a genuine boolean attribute. Never used to represent `FactStatus`."""
    return BooleanValue(flag)
