"""Medication alignment.

The patient says "Metformin". The prescription says "Tab. Metformin 900.2 mg BD".
Both are on the record — one on the voice channel as `current_medications`, one
on the document channel as `medication_metformin` — and because they carry
different field ids, the contradiction detector cannot see that they are about
the same drug.

Which means the dose discrepancy, which is the single most useful thing the
document pipeline can surface, goes unreported, and the prescription instead
shows up as "the patient did not mention this medicine" — an unhelpful line
about a medicine they *did* mention.

This module fixes that by deriving an **alias fact**: for every voice medication
fact whose text resolves to a known ingredient, a voice-channel fact keyed
`medication_<ingredient>`, carrying the same value, the same source and the same
certainty as the original.

Three properties keep this honest:

- **It adds nothing.** The alias carries the original's value verbatim; it does
  not parse a dose out of it, does not normalise the name, and does not raise
  certainty. It is the same claim under a comparable name.
- **It resolves nothing.** An alias whose name does not appear in the ingredient
  table is not produced. A guess here would attach a patient's words to the
  wrong drug.
- **It is derived, and says so.** Every alias carries `note="alias_of=<fact_id>"`
  and a fact id derived from its source, so it is traceable back and cannot be
  mistaken for a second, independent statement by the patient.

Pure. No clock, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.clinical.enums import Section
from app.domain.documents.ingredients import IngredientIndex
from app.domain.record import Fact, FieldStatus

#: Voice fields that hold a free-text medication list.
MEDICATION_FIELDS: frozenset[str] = frozenset(
    {"current_medications", "ayurvedic_medications"}
)

ALIAS_NOTE_PREFIX = "alias_of="


def _alias_id(fact_id: str, ingredient: str) -> str:
    """Deterministic, and visibly derived from its source."""
    return f"{fact_id}~{ingredient}"


def is_alias(fact: Fact) -> bool:
    return bool(fact.note and fact.note.startswith(ALIAS_NOTE_PREFIX))


def align_medications(
    facts: Sequence[Fact], ingredients: IngredientIndex
) -> tuple[Fact, ...]:
    """Alias facts for every resolvable voice medication.

    Returns only the *new* facts. The caller appends them to the record it is
    about to run detection over; they are never persisted, because they are
    derived and a stored derivation is a second thing to keep in sync.
    """
    # Voice-channel field ids only. A `medication_metformin` fact already on the
    # *document* channel is precisely what the alias exists to be compared
    # against — treating it as "already present" would skip the alias and leave
    # the dose discrepancy unreported, which is the bug this module was written
    # to fix.
    existing = {f.field_id for f in facts if f.is_from_today}
    aliases: list[Fact] = []

    for fact in facts:
        if fact.field_id not in MEDICATION_FIELDS:
            continue
        if not fact.is_from_today or fact.status is not FieldStatus.ANSWERED:
            continue
        source_text = fact.rendered_value() or fact.original_text
        if not source_text:
            continue

        for name in _candidate_names(source_text):
            key = ingredients.resolve(name)
            if key is None:
                continue
            field_id = f"medication_{key}"
            if field_id in existing:
                continue
            existing.add(field_id)
            aliases.append(
                fact.model_copy(
                    update={
                        "fact_id": _alias_id(fact.fact_id, key),
                        "field_id": field_id,
                        "section": Section.MEDICATIONS,
                        "note": f"{ALIAS_NOTE_PREFIX}{fact.fact_id}",
                    }
                )
            )
    return tuple(aliases)


def _candidate_names(text: str) -> tuple[str, ...]:
    """The medicine names a free-text answer might contain.

    A patient listing three medicines produces one string. Splitting on the
    separators people actually use — commas, "and", "aur", newlines — gives each
    a chance to resolve. A fragment that resolves to nothing contributes
    nothing, which is the safe failure.
    """
    normalised = (
        text.replace(" and ", ",").replace(" aur ", ",").replace(" और ", ",")
    )
    parts = [
        part.strip()
        for chunk in normalised.splitlines()
        for part in chunk.split(",")
        if part.strip()
    ]
    # The whole string too: a single medicine with a strength — "Metformin 500" —
    # is one candidate, not two.
    return (text.strip(), *parts) if parts else (text.strip(),)
