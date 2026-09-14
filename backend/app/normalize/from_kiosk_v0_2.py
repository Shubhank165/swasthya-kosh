"""Normalizer: kiosk schema_version 0.2 -> `CanonicalRecord`.

0.2 differs from 0.1 in exactly one way — a field outcome may carry
`carried_forward` — so this file differs from `from_kiosk_v0_1` in exactly one
way too. Everything else is imported from it rather than copied: two
normalizers that each decide independently what a `duration` means is the
failure mode the golden fixtures exist to catch, and the cheapest way to never
have it is to not write the second implementation.

Two things a carried-forward fact must get right, and both are about not
overstating what is known:

- **Its channel is `PRIOR_RECORD`, not `VOICE`.** The contradiction detector
  compares what the patient says today against what we already held, and a
  June answer filed under "today" would compare against itself and never
  conflict with anything.
- **Its certainty does not rise because it was confirmed.** A patient saying
  "yes, still" today is a report, exactly as it was in June. Promoting it would
  be the certainty increase `app.domain.record` refuses everywhere else, made
  by a normalizer where nobody would look for it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.contracts.kiosk.v0_2 import SCHEMA_VERSION, KioskFieldV0_2, KioskIntakeV0_2
from app.domain.clinical.enums import ReporterRole
from app.domain.clinical.sections import section_for
from app.domain.record import (
    CanonicalRecord,
    CarriedForward,
    EntrySource,
    Fact,
    FactChannel,
    FieldStatus,
    IngestProvenance,
    IntakeStatus,
    RedFlagEvent,
)
from app.normalize.from_kiosk_v0_1 import (
    _fact_from_field,
    _patient_ref,
    _reporter,
    _turn_index,
    fact_id_for,
    intake_uuid,
)
from app.normalize.values import certainty_for, coerce


def _carried_fact(
    *,
    intake_id: str,
    field_id: str,
    field: KioskFieldV0_2,
    default_language: str,
    reporter: ReporterRole,
    recorded_at: datetime,
) -> Fact:
    """One answer brought over from a previous visit.

    The `EntrySource` names the prior intake, so the evidence panel can link to
    it (3/3 §5) — the provenance on `carried_forward` says how old the answer
    is, and the source says where to go and read it. Both, because they answer
    different questions.
    """
    assert field.carried_forward is not None
    carried = field.carried_forward
    return Fact(
        # The ordinal distinguishes this from a voice fact on the same field: a
        # patient may both have diabetes carried forward *and* mention it today,
        # and those are two facts the detector must be able to compare.
        fact_id=fact_id_for(intake_id, field_id, FactChannel.PRIOR_RECORD.value),
        field_id=field_id,
        status=FieldStatus(field.status),
        value=coerce(field.value, unit_hint=field.unit),
        original_text=field.original_text,
        language=field.language or default_language,
        source=EntrySource(
            entered_by="carried_forward", prior_intake_id=carried.from_intake_id
        ),
        confidence=field.confidence,
        reported_by=reporter,
        # Confirming an old answer does not make it new evidence.
        certainty=certainty_for(field.original_text, field.confidence),
        section=section_for(field_id, field.section),
        channel=FactChannel.PRIOR_RECORD,
        carried_forward=CarriedForward(
            from_intake_id=carried.from_intake_id,
            originally_recorded=carried.originally_recorded,
            confirmed_today=carried.confirmed_today,
        ),
        recorded_at=recorded_at,
    )


def normalize(payload: Mapping[str, Any], *, now: datetime) -> CanonicalRecord:
    """Map a validated 0.2 payload to the canonical record."""
    parsed = KioskIntakeV0_2.model_validate(payload)
    turns = _turn_index(parsed.turns)
    reporter = _reporter(parsed.reporter)
    recorded_at = parsed.completed_at or parsed.started_at or now

    facts: list[Fact] = []
    for field_id, field in sorted(parsed.fields.items()):
        if field.carried_forward is not None:
            facts.append(
                _carried_fact(
                    intake_id=parsed.intake_id,
                    field_id=field_id,
                    field=field,
                    default_language=parsed.language,
                    reporter=reporter,
                    recorded_at=recorded_at,
                )
            )
            continue
        facts.append(
            _fact_from_field(
                intake_id=parsed.intake_id,
                field_id=field_id,
                field=field,
                turns=turns,
                default_language=parsed.language,
                reporter=reporter,
                recorded_at=recorded_at,
            )
        )

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
