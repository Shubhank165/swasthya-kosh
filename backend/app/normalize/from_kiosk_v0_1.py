"""Normalizer: kiosk schema_version 0.1 -> `CanonicalRecord`.

One file per input version. Pure — no clock, no database, no model, no network —
which is what lets `tests/contracts/` assert the whole mapping against a golden
fixture and lets a golden-file diff be a readable review of a schema change.

The mapping is deliberately dull. Every interesting decision was made in
`app.domain.record`; this file's only job is to carry the payload across without
adding anything. Two things it must not do:

- **It must not resolve a status.** `unresolved` stays `unresolved`. There is no
  branch here that turns a missing answer into `no`, and adding one would defeat
  the entire record model.
- **It must not drop what it does not understand.** An unrecognised field id
  gets a section from the fallback table and is kept; an unparseable value
  becomes `Text` carrying the original.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.contracts.kiosk.v0_1 import SCHEMA_VERSION, KioskField, KioskIntakeV0_1, KioskTurn
from app.domain.clinical.enums import ReporterRole
from app.domain.clinical.sections import section_for
from app.domain.record import (
    CanonicalRecord,
    Fact,
    FactChannel,
    FieldStatus,
    IngestProvenance,
    IntakeStatus,
    PatientRef,
    PatientRefType,
    RedFlagEvent,
    TurnSource,
)
from app.normalize.values import certainty_for, coerce

#: Namespace for deterministic fact ids. Ids must be a pure function of the
#: payload: a replayed ingest has to produce byte-identical facts, or
#: idempotency is a lie and the golden fixtures churn on every run.
_FACT_NAMESPACE = uuid5(NAMESPACE_URL, "https://medikiosk.in/facts")


def fact_id_for(intake_id: str, field_id: str, channel: str, ordinal: int = 0) -> str:
    """A stable id for one fact of one intake."""
    stem = f"{intake_id}/{channel}/{field_id}/{ordinal}"
    return f"fact_{uuid5(_FACT_NAMESPACE, stem)}"


def intake_uuid(raw: str) -> UUID:
    """The intake's UUID.

    The kiosk is specified to send a UUID. When it sends something else — a
    device-local counter, a hostname-prefixed string — we derive a stable UUID
    from it rather than rejecting the intake, because the identifier format is
    not worth losing a completed interview over. The original travels on
    `provenance.kiosk_id` and in `ingest_raw`.
    """
    try:
        return UUID(raw)
    except ValueError:
        return uuid5(_FACT_NAMESPACE, f"intake/{raw}")


def _reporter(raw: str) -> ReporterRole:
    try:
        return ReporterRole(raw)
    except ValueError:
        # An unknown reporter is weaker evidence than a self-report, not
        # stronger. Falling back to SELF would overstate it.
        return ReporterRole.FAMILY_ATTENDANT


def _patient_ref(raw_type: str, raw_value: str | None) -> PatientRef:
    try:
        ref_type = PatientRefType(raw_type)
    except ValueError:
        return PatientRef(type=PatientRefType.GUEST)
    if ref_type is PatientRefType.GUEST or not raw_value:
        return PatientRef(type=PatientRefType.GUEST)
    if ref_type is PatientRefType.AADHAAR_LAST4:
        # Defence in depth: the contract says four digits, but a device that
        # sends the whole number must not have it stored. Keep the last four.
        digits = "".join(ch for ch in raw_value if ch.isdigit())
        return PatientRef(type=ref_type, value=digits[-4:] if len(digits) >= 4 else None) if (
            len(digits) >= 4
        ) else PatientRef(type=PatientRefType.GUEST)
    return PatientRef(type=ref_type, value=raw_value)


def _turn_index(turns: list[KioskTurn]) -> Mapping[int, KioskTurn]:
    return {turn.turn_id: turn for turn in turns}


def _source_for(
    field_id: str, field: KioskField, turns: Mapping[int, KioskTurn]
) -> TurnSource:
    """The turn a field's answer came from.

    A field with no `source_turn` still gets a source: turn 0, meaning "the
    device asserted this without telling us which turn produced it". Every fact
    carries provenance (hard rule 5), even when that provenance is an admission
    that the device did not say.
    """
    turn = turns.get(field.source_turn) if field.source_turn is not None else None
    if turn is None:
        return TurnSource(turn_id=field.source_turn or 0, question_id=None)
    return TurnSource(
        turn_id=turn.turn_id,
        question_id=turn.question_id,
        transcript_excerpt=turn.transcript,
    )


def _fact_from_field(
    *,
    intake_id: str,
    field_id: str,
    field: KioskField,
    turns: Mapping[int, KioskTurn],
    default_language: str,
    reporter: ReporterRole,
    recorded_at: datetime,
) -> Fact:
    status = FieldStatus(field.status)
    value = coerce(field.value, unit_hint=field.unit) if status is FieldStatus.ANSWERED else None
    turn = turns.get(field.source_turn) if field.source_turn is not None else None
    original_text = field.original_text or (turn.transcript if turn is not None else None)
    return Fact(
        fact_id=fact_id_for(intake_id, field_id, FactChannel.VOICE.value),
        field_id=field_id,
        status=status,
        value=value,
        original_text=original_text,
        language=field.language or (turn.language if turn is not None else None) or (
            default_language
        ),
        source=_source_for(field_id, field, turns),
        confidence=field.confidence
        if field.confidence is not None
        else (turn.asr_confidence if turn is not None else None),
        reported_by=reporter,
        certainty=certainty_for(original_text, field.confidence),
        section=section_for(field_id, field.section),
        channel=FactChannel.VOICE,
        recorded_at=recorded_at,
    )


def normalize(payload: Mapping[str, Any], *, now: datetime) -> CanonicalRecord:
    """Map a validated 0.1 payload to the canonical record.

    Raises `pydantic.ValidationError` when the payload does not satisfy the 0.1
    contract. The caller — `app.services.ingest` — routes that to the repair
    path rather than rejecting the intake.
    """
    parsed = KioskIntakeV0_1.model_validate(payload)
    turns = _turn_index(parsed.turns)
    reporter = _reporter(parsed.reporter)
    # Prefer the device's own clock for the record's timestamps: the interview
    # happened when the device says it happened, not when the network recovered
    # and the payload finally arrived.
    recorded_at = parsed.completed_at or parsed.started_at or now

    facts = [
        _fact_from_field(
            intake_id=parsed.intake_id,
            field_id=field_id,
            field=field,
            turns=turns,
            default_language=parsed.language,
            reporter=reporter,
            recorded_at=recorded_at,
        )
        for field_id, field in sorted(parsed.fields.items())
    ]

    red_flags = [
        RedFlagEvent(
            rule_id=flag.rule_id,
            fired_at_turn=flag.fired_at_turn,
            criteria_met=tuple(flag.criteria_met),
            severity=flag.severity,
            label=flag.label,
        )
        for flag in parsed.red_flags
    ]

    return CanonicalRecord(
        intake_id=intake_uuid(parsed.intake_id),
        hospital_id=parsed.hospital_id,
        patient_ref=_patient_ref(parsed.patient_ref.type, parsed.patient_ref.value),
        language=parsed.language,
        status=IntakeStatus(parsed.status),
        reported_by=reporter,
        department_code=parsed.department_code,
        facts=facts,
        red_flags=red_flags,
        documents=[],
        contradictions=[],
        provenance=IngestProvenance(
            schema_version=SCHEMA_VERSION,
            engine_version=parsed.engine_version,
            content_version=parsed.content_version,
            kiosk_id=parsed.kiosk_id,
        ),
        started_at=parsed.started_at,
        completed_at=parsed.completed_at,
        created_at=now,
        updated_at=now,
    )


def payload_fingerprint(payload: Mapping[str, Any]) -> str:
    """Stable hash of a raw payload, for the `ingest_raw` table."""
    import json

    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
