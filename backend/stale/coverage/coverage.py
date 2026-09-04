"""Coverage engine.

Computes what the intake owed, what it captured and what is still missing, from
the pathway definitions rather than from anyone's opinion. The dashboard gets
both the percentage and the actual list of missing fields, because "92%" tells a
doctor nothing and "allergy history not asked" tells them exactly what to do.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.domain.clinical.enums import SECTION_ORDER, FactStatus, Section
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.statemachine.selectors import PlannedField, is_owed


@dataclass(frozen=True, slots=True)
class MissingField:
    """A field the intake owed and did not get."""

    concept: str
    section: Section
    required: bool
    #: `not_asked` (never put) or `blocked` (applicable but unanswered mid-session).
    reason: str

    def describe(self) -> str:
        label = self.concept.replace("_", " ")
        return f"{label} not asked" if self.reason == "not_asked" else f"{label} unanswered"


@dataclass(frozen=True, slots=True)
class SectionCoverage:
    """Per-section counts. `not_applicable` is a real outcome, not a gap."""

    section: Section
    required: int
    captured: int
    not_applicable: int
    unanswered: int
    declined: int
    missing: tuple[MissingField, ...] = field(default_factory=tuple)

    @property
    def denominator(self) -> int:
        """Required fields that could actually be asked."""
        return max(self.required - self.not_applicable, 0)

    @property
    def percentage(self) -> float:
        """0.0..100.0. A section with nothing to ask is 100% complete, not 0%."""
        if self.denominator == 0:
            return 100.0
        return round(100.0 * (self.captured + self.declined) / self.denominator, 1)

    @property
    def is_complete(self) -> bool:
        return self.unanswered == 0


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Whole-intake coverage."""

    sections: tuple[SectionCoverage, ...]
    required_total: int
    required_captured: int
    required_not_applicable: int
    required_declined: int
    optional_captured: int
    optional_total: int

    @property
    def denominator(self) -> int:
        return max(self.required_total - self.required_not_applicable, 0)

    @property
    def percentage(self) -> float:
        if self.denominator == 0:
            return 100.0
        return round(
            100.0 * (self.required_captured + self.required_declined) / self.denominator, 1
        )

    @property
    def is_complete(self) -> bool:
        """True when nothing required is still owed. This — not a percentage and
        not a timer — is what permits the intake to move to READY."""
        return all(s.is_complete for s in self.sections)

    def missing(self) -> tuple[MissingField, ...]:
        """Every gap, required first, in clinical section order."""
        gaps = [m for s in self.sections for m in s.missing]
        return tuple(sorted(gaps, key=lambda m: (not m.required, SECTION_ORDER.index(m.section))))

    def missing_required(self) -> tuple[MissingField, ...]:
        return tuple(m for m in self.missing() if m.required)

    def section(self, section: Section) -> SectionCoverage | None:
        for entry in self.sections:
            if entry.section is section:
                return entry
        return None


def compute(
    state: PatientIntakeState, plan: Sequence[PlannedField]
) -> CoverageReport:
    """Coverage of `state` against `plan`.

    A field counts as captured when it holds PRESENT, ABSENT or UNKNOWN: "I don't
    know" is a captured answer, and treating it as a gap would send the kiosk
    round in circles asking a question the patient cannot answer.
    """
    by_section: dict[Section, list[PlannedField]] = {}
    for planned in plan:
        by_section.setdefault(planned.section, []).append(planned)

    sections: list[SectionCoverage] = []
    required_total = required_captured = required_na = required_declined = 0
    optional_total = optional_captured = 0

    for section in SECTION_ORDER:
        entries = by_section.get(section)
        if not entries:
            continue
        req = cap = na = unanswered = declined = 0
        missing: list[MissingField] = []
        for planned in entries:
            status = state.status_of(planned.concept)
            is_declined = planned.concept in state.declined
            captured = status in {FactStatus.PRESENT, FactStatus.ABSENT, FactStatus.UNKNOWN}
            not_applicable = status is FactStatus.NOT_APPLICABLE

            if planned.required:
                req += 1
                if captured:
                    cap += 1
                elif not_applicable:
                    na += 1
                elif is_declined:
                    declined += 1
                else:
                    unanswered += 1
                    missing.append(
                        MissingField(
                            concept=planned.concept,
                            section=section,
                            required=True,
                            reason=(
                                "not_asked"
                                if status is FactStatus.NOT_ASKED
                                else "blocked"
                            ),
                        )
                    )
            else:
                optional_total += 1
                if captured:
                    optional_captured += 1
                elif is_owed(state, planned):
                    missing.append(
                        MissingField(
                            concept=planned.concept,
                            section=section,
                            required=False,
                            reason="not_asked",
                        )
                    )

        sections.append(
            SectionCoverage(
                section=section,
                required=req,
                captured=cap,
                not_applicable=na,
                unanswered=unanswered,
                declined=declined,
                missing=tuple(missing),
            )
        )
        required_total += req
        required_captured += cap
        required_na += na
        required_declined += declined

    return CoverageReport(
        sections=tuple(sections),
        required_total=required_total,
        required_captured=required_captured,
        required_not_applicable=required_na,
        required_declined=required_declined,
        optional_captured=optional_captured,
        optional_total=optional_total,
    )
