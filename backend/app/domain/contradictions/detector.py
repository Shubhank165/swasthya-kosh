"""Contradiction detection.

Compares what the patient said during the intake against what was read off their
documents and carried forward from prior records. When the two disagree it says
so and stops.

It never picks a winner. Deciding which of two conflicting histories is true is a
clinical act, and the entire value of surfacing the conflict is destroyed if
software silently resolves it — the physician would never learn there had been
anything to resolve.

The algorithm is carried over from the previous build unchanged; only the fact
type it reads changed, from `ClinicalFact` to the canonical `Fact`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.domain.record import (
    Boolean,
    ConflictKind,
    ConflictSide,
    Contradiction,
    Fact,
    FieldStatus,
)

#: Field families where a conflict is clinically material. Everything else is
#: noise, and noise is how a physician learns to skip the conflicts section: a
#: pain score that moved from 6 to 7 is not a contradiction worth a line.
DEFAULT_WATCHED_PREFIXES: tuple[str, ...] = (
    "condition_",
    "allergy_",
    "medication_",
    "surgery_",
    "diagnosis_",
)

# `lab_` is deliberately absent. A lab value appears only on the document
# channel — nobody expects a patient to recite their own haemoglobin — so every
# result would fire PRESENCE_ONLY_IN_RECORD and the conflicts section would fill
# with rows saying the patient did not mention a number they were never asked
# for. Lab results belong under Prior Investigations, where they are already
# printed with their own reference ranges.

#: Individual fields always watched, regardless of prefix.
DEFAULT_WATCHED_FIELDS: frozenset[str] = frozenset(
    {
        "known_diabetes",
        "known_hypertension",
        "known_thyroid_disorder",
        "known_asthma",
        "drug_allergy",
        "food_allergy",
        "current_medications",
        "ayurvedic_medications",
        "past_surgery",
        "pregnancy",
    }
)


def is_watched(
    field_id: str, *, prefixes: Sequence[str], fields: frozenset[str]
) -> bool:
    """True when a conflict on this field is worth a physician's attention."""
    return field_id in fields or any(field_id.startswith(p) for p in prefixes)


def _statement_of(fact: Fact, labels: Mapping[str, str] | None = None) -> str:
    """How this fact reads inside a conflict block."""
    label = (labels or {}).get(fact.field_id) or fact.field_id.replace("_", " ")
    if fact.denies():
        return f"denies {label}"
    if fact.status is FieldStatus.UNRESOLVED:
        return f"unsure about {label}"
    rendered = fact.rendered_value()
    return f"{label}: {rendered}" if rendered is not None else label


def _side(fact: Fact, labels: Mapping[str, str] | None = None) -> ConflictSide:
    return ConflictSide(
        fact_id=fact.fact_id,
        statement=_statement_of(fact, labels),
        channel=fact.channel,
        source_label=fact.source_label(),
        confidence=fact.confidence,
        original_text=fact.original_text,
    )


def _conflicting(today: Fact, record: Fact) -> ConflictKind | None:
    """The kind of conflict between two facts, or `None` when they agree.

    Only two `answered` facts can conflict. A patient who could not remember has
    not contradicted anything, and a field that was never asked contradicts even
    less — flagging either would bury the real conflicts in noise and is exactly
    the collapse of the status vocabulary that hard rule 2 forbids.
    """
    if today.status is not FieldStatus.ANSWERED or record.status is not FieldStatus.ANSWERED:
        return None

    today_bool = isinstance(today.value, Boolean)
    record_bool = isinstance(record.value, Boolean)
    if today_bool and record_bool:
        assert isinstance(today.value, Boolean) and isinstance(record.value, Boolean)
        return ConflictKind.STATUS if today.value.value != record.value.value else None

    # One side asserts a value, the other denies the field outright.
    if today.denies() != record.denies():
        return ConflictKind.STATUS

    today_value = today.rendered_value()
    record_value = record.rendered_value()
    if today_value is not None and record_value is not None and today_value != record_value:
        return ConflictKind.VALUE
    return None


def detect(
    facts: Sequence[Fact],
    *,
    watched_prefixes: Sequence[str] = DEFAULT_WATCHED_PREFIXES,
    watched_fields: frozenset[str] = DEFAULT_WATCHED_FIELDS,
    report_unmentioned: bool = True,
    labels: Mapping[str, str] | None = None,
) -> tuple[Contradiction, ...]:
    """Every material disagreement in `facts`, in field order.

    `facts` is the live view — one revision per fact — but **both channels**.
    Collapsing to one fact per field before calling this would delete one half
    of every conflict, which is the mistake that makes a scanned prescription
    silently overwrite what the patient said.
    """
    today_by_field: dict[str, Fact] = {}
    record_by_field: dict[str, list[Fact]] = {}
    for fact in facts:
        if not is_watched(fact.field_id, prefixes=watched_prefixes, fields=watched_fields):
            continue
        if fact.is_from_today:
            today_by_field[fact.field_id] = fact
        elif fact.is_from_record:
            record_by_field.setdefault(fact.field_id, []).append(fact)

    found: list[Contradiction] = []
    for field_id in sorted(record_by_field):
        today = today_by_field.get(field_id)
        for record in sorted(record_by_field[field_id], key=lambda f: f.fact_id):
            if today is None:
                # The record holds something the patient did not mention. Not a
                # contradiction, but the physician still needs to see it — a
                # medicine on last month's prescription that the patient did not
                # list today is either stopped or forgotten, and only they can
                # say which.
                if report_unmentioned and record.is_established:
                    found.append(
                        Contradiction(
                            field_id=field_id,
                            kind=ConflictKind.PRESENCE_ONLY_IN_RECORD,
                            reported_today=None,
                            from_record=_side(record, labels),
                        )
                    )
                continue
            kind = _conflicting(today, record)
            if kind is not None:
                found.append(
                    Contradiction(
                        field_id=field_id,
                        kind=kind,
                        reported_today=_side(today, labels),
                        from_record=_side(record, labels),
                    )
                )
    return tuple(found)
