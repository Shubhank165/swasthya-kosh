"""Identifier types and the concept reference.

The evidence carriers — `TurnSource`, `DocumentSource`, `BoundingBox` — live in
`app.domain.record`, because they are part of the canonical record's versioned
surface. What stays here is the vocabulary shared by the ontology and the
terminology service: the concept reference, and the typed identifiers that keep
an intake id from being passed where a document id belongs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

FactId = NewType("FactId", str)
IntakeId = NewType("IntakeId", str)
DocumentId = NewType("DocumentId", str)
ReportId = NewType("ReportId", str)
UserId = NewType("UserId", str)
PatientId = NewType("PatientId", str)
HospitalId = NewType("HospitalId", str)


@dataclass(frozen=True, slots=True)
class ConceptRef:
    """A normalised clinical concept plus, optionally, the coded terminology it
    resolves to.

    `code` stays `None` when no mapping exists — we never invent one. A guessed
    ICD code on a discharge summary is a billing error at best and a wrong
    diagnosis in someone's permanent record at worst.
    """

    concept_id: str
    system: str | None = None
    code: str | None = None
    display: str | None = None

    def __post_init__(self) -> None:
        if not self.concept_id:
            raise ValueError("concept_id must not be empty")

    @property
    def label(self) -> str:
        """How this concept reads in a report line."""
        return self.display or self.concept_id.replace("_", " ")

    def __str__(self) -> str:
        return self.concept_id
