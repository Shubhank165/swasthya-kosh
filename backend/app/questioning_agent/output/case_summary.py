"""The case, for the practitioner — §29.

**Three kinds of statement, kept apart on the page.**

    patient reported     they chose it or typed it
    system read          a parser took it out of a sentence
    clinician assesses   nobody has filled this in; it is yours

That separation is the point of the whole document. "The patient said three
days" and "a regular expression found three days in a sentence" are different
claims, and a practitioner deciding what to do about a case has to be able to
see which one they are looking at before they act on it.

**Nothing here is a diagnosis and nothing here says one.** There is no
impression, no differential and no suggestion. The uncertain and unanswered
section is not an apology — it is a list of the things the practitioner now
knows to ask about, which is the most useful thing an intake can hand over
short of the answers themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.questioning_agent.core.enums import Certainty, Provenance
from app.questioning_agent.core.patient_state import PatientState
from app.questioning_agent.core.schemas import CaseValue, RedFlag
from app.questioning_agent.knowledge.information_schema import SlotRegistry


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    values: tuple[CaseValue, ...]


@dataclass
class CaseSummary:
    """A structured case. Rendering is somebody else's job."""

    chief_complaint: str | None
    active_domains: tuple[str, ...]
    sections: tuple[Section, ...]
    #: Slots the parser could not read, with what the patient said.
    uncertain: tuple[CaseValue, ...] = ()
    #: Slots nobody filled, worth asking about in the room.
    unanswered: tuple[str, ...] = ()
    #: Empty until the practitioner writes in them.
    clinician_assessed: tuple[str, ...] = ()
    red_flags: tuple[RedFlag, ...] = ()
    #: Every answer as it was given. §20 — never discarded.
    verbatim: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def stopped_early(self) -> bool:
        return bool(self.red_flags)


def build(state: PatientState, slots: SlotRegistry) -> CaseSummary:
    """Assemble the case from what is known. No model, no inference.

    Every line traces to a slot that was filled, and every filled slot carries
    where it came from. There is nothing in here that was generated.
    """
    by_domain: dict[str, list[CaseValue]] = {}
    for slot_id, fact in state.known_facts.items():
        if slot_id.startswith("routing."):
            continue
        slot = slots.get(slot_id)
        if slot is None:
            continue
        by_domain.setdefault(slot.domain, []).append(
            CaseValue(
                slot=slot_id,
                value=fact.value,
                provenance=fact.provenance,
                certainty=fact.certainty,
                evidence=fact.evidence,
            )
        )

    # The complaint first, then the other active domains, then the history that
    # is asked of everyone. A practitioner reads the reason for the visit before
    # they read the diet.
    order: list[str] = []
    if state.chief_complaint:
        order.append(state.chief_complaint)
    order.extend(d for d in state.active_domains if d not in order)
    order.extend(d for d in ("general", "ayush") if d in by_domain and d not in order)
    order.extend(d for d in sorted(by_domain) if d not in order)

    sections = tuple(
        Section(
            title=domain,
            values=tuple(sorted(by_domain[domain], key=lambda v: v.slot)),
        )
        for domain in order
        if by_domain.get(domain)
    )

    uncertain = tuple(
        CaseValue(
            slot=fact.slot,
            value=None,
            provenance=fact.provenance,
            certainty=Certainty.UNCERTAIN,
            evidence=fact.evidence,
        )
        for fact in sorted(state.uncertain_facts.values(), key=lambda f: f.slot)
    )

    # Worth asking about in the room: high-priority slots for the domains the
    # patient is actually here about, which nobody filled. Deliberately not
    # every empty slot — a list of 200 is a list nobody reads.
    unanswered = tuple(
        sorted(
            slot.id
            for slot in slots.askable()
            if not state.knows(slot.id)
            and slot.id not in state.uncertain_facts
            and slot.priority >= 8
            and (slot.domain in state.active_domains or slot.required)
        )
    )

    return CaseSummary(
        chief_complaint=state.chief_complaint,
        active_domains=state.active_domains,
        sections=sections,
        uncertain=uncertain,
        unanswered=unanswered,
        clinician_assessed=tuple(
            sorted(s.id for s in slots.all if not s.patient_observable)
        ),
        red_flags=tuple(state.red_flags),
        verbatim=tuple(
            (record.question_id, record.raw_response) for record in state.raw_responses
        ),
    )


def render(summary: CaseSummary, slots: SlotRegistry) -> str:
    """A plain-text case sheet.

    For a terminal, a test fixture and a first look at what the engine
    collected. The real one is whatever the dashboard chooses to draw from the
    structure above; this exists so the structure can be read without one.
    """
    lines: list[str] = []

    if summary.red_flags:
        lines.append("URGENT — clinical review criteria triggered")
        for flag in summary.red_flags:
            lines.append(f"  [{flag.severity}] {flag.id}")
        lines.append("  The questionnaire was stopped here.")
        lines.append("")

    lines.append(f"Chief complaint: {summary.chief_complaint or '—'}")
    if summary.active_domains:
        lines.append(f"Reported problems: {', '.join(summary.active_domains)}")
    lines.append("")

    for section in summary.sections:
        lines.append(f"{section.title.replace('_', ' ').title()}")
        for value in section.values:
            slot = slots.get(value.slot)
            label = slot.description if slot else value.slot
            mark = _mark(value)
            lines.append(f"  {label}: {_render_value(value.value)}{mark}")
        lines.append("")

    if summary.uncertain:
        lines.append("Could not be read — worth asking directly")
        for value in summary.uncertain:
            slot = slots.get(value.slot)
            label = slot.description if slot else value.slot
            said = f' (patient said: "{value.evidence}")' if value.evidence else ""
            lines.append(f"  {label}{said}")
        lines.append("")

    if summary.unanswered:
        lines.append("Not answered")
        for slot_id in summary.unanswered:
            slot = slots.get(slot_id)
            lines.append(f"  {slot.description if slot else slot_id}")
        lines.append("")

    lines.append("For the practitioner to assess")
    for slot_id in summary.clinician_assessed:
        slot = slots.get(slot_id)
        lines.append(f"  {slot.description if slot else slot_id}: —")
    lines.append("")

    lines.append("Key: * read from the patient's own words rather than chosen")
    lines.append("     ? the patient was unsure")
    return "\n".join(lines)


def _mark(value: CaseValue) -> str:
    marks = ""
    if value.provenance is Provenance.SYSTEM_NORMALISED:
        marks += " *"
    if value.certainty is Certainty.PROBABLE:
        marks += " ?"
    return marks


def _render_value(value: object) -> str:
    if isinstance(value, dict) and "value" in value and "unit" in value:
        about = "about " if value.get("approximate") else ""
        return f"{about}{_trim(value['value'])} {value['unit']}"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v).replace("_", " ") for v in value) or "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return _trim(value)
    return str(value).replace("_", " ")


def _trim(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


__all__ = ["CaseSummary", "Section", "build", "render"]
