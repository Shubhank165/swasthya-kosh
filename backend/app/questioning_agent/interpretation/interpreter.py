"""One answer in, facts out — §13.

Dispatches on the question's answer type to the parser that knows how to read
it, then resolves `*` targets against the active domains so a single sentence
about onset fills the onset slot of every domain in play.

**The raw response is kept whatever happens**, and it is kept by the caller
before this is called, so a parser that raises still leaves the patient's words
in the record. That is §20, and it is the difference between a wrong extraction
somebody can find and one nobody can.
"""

from __future__ import annotations

from app.questioning_agent.core.enums import AnswerType, Certainty, Provenance
from app.questioning_agent.core.patient_state import PatientState
from app.questioning_agent.core.schemas import ParsedFact, Question, ResponseRecord
from app.questioning_agent.interpretation.boolean_parser import parse_boolean
from app.questioning_agent.interpretation.duration_parser import parse_duration
from app.questioning_agent.interpretation.free_text_parser import parse_free_text
from app.questioning_agent.interpretation.numeric_parser import parse_numeric
from app.questioning_agent.interpretation.option_parser import (
    parse_multi_select,
    parse_single_select,
)
from app.questioning_agent.knowledge.information_schema import SlotRegistry
from app.questioning_agent.localization.languages import Vocabulary
from app.questioning_agent.localization.localization_loader import Localization


class Interpreter:
    def __init__(self, slots: SlotRegistry, localization: Localization) -> None:
        self._slots = slots
        # Held so an option can be matched by the wording the patient was
        # actually shown, in whatever language they were shown it in.
        self._localization = localization

    def interpret(
        self,
        question: Question,
        response: str,
        state: PatientState,
        vocabulary: Vocabulary,
    ) -> ResponseRecord:
        """Read one answer. Never raises, never invents."""
        targets = self._targets(question, state)
        facts = self._facts(question, response, targets, state, vocabulary)
        return ResponseRecord(
            question_id=question.id,
            raw_response=response,
            facts=facts,
        )

    # --- internals -----------------------------------------------------------

    def _targets(self, question: Question, state: PatientState) -> tuple[str, ...]:
        """`*.onset` -> one slot per active domain that has one."""
        out: list[str] = []
        for target in question.extracts:
            if target.startswith("*."):
                local = target.split(".", 1)[1]
                out.extend(
                    f"{domain}.{local}"
                    for domain in state.active_domains
                    if f"{domain}.{local}" in self._slots
                )
            else:
                out.append(target)
        return tuple(dict.fromkeys(out))

    def _facts(
        self,
        question: Question,
        response: str,
        targets: tuple[str, ...],
        state: PatientState,
        vocabulary: Vocabulary,
    ) -> tuple[ParsedFact, ...]:
        if not targets:
            return ()

        match question.answer_type:
            case AnswerType.BOOLEAN:
                return tuple(
                    parse_boolean(response, target, vocabulary) for target in targets
                )

            case AnswerType.SINGLE_SELECT:
                options = self._options(question, state)
                labels = self._labels(options, vocabulary.language)
                return tuple(
                    parse_single_select(response, target, options, vocabulary, labels)
                    for target in targets
                )

            case AnswerType.MULTI_SELECT:
                options = self._options(question, state)
                labels = self._labels(options, vocabulary.language)
                return tuple(
                    parse_multi_select(response, target, options, vocabulary, labels)
                    for target in targets
                )

            case AnswerType.NUMERIC | AnswerType.SCALE:
                return tuple(
                    parse_numeric(
                        response,
                        target,
                        vocabulary,
                        unit=question.unit,
                        units=question.units,
                        minimum=question.minimum,
                        maximum=question.maximum,
                    )
                    for target in targets
                )

            case AnswerType.DURATION:
                return tuple(
                    parse_duration(response, target, vocabulary) for target in targets
                )

            case AnswerType.DATE:
                return tuple(_date_fact(response, target) for target in targets)

            case AnswerType.FREE_TEXT | AnswerType.STRUCTURED_TEXT:
                return parse_free_text(
                    response,
                    targets,
                    self._slots,
                    vocabulary,
                    labels=self._all_labels(targets, vocabulary.language),
                )

        return ()

    def _labels(self, options: tuple[str, ...], language: str) -> dict[str, str]:
        """Each option's own wording, in the language it was shown in."""
        return {
            option: self._localization.option_text(option, language)
            for option in options
            if self._localization.has_option(option, language)
        }

    def _all_labels(self, targets: tuple[str, ...], language: str) -> dict[str, str]:
        """Labels for every code a free-text answer could name."""
        options: list[str] = []
        for target in targets:
            slot = self._slots.get(target)
            if slot is not None:
                options.extend(slot.allowed_values)
        return self._labels(tuple(dict.fromkeys(options)), language)

    def _options(self, question: Question, state: PatientState) -> tuple[str, ...]:
        """A question's options, including the one that gets them at runtime."""
        if question.options_from:
            value = state.value(question.options_from)
            if isinstance(value, (list, tuple)):
                return tuple(str(v) for v in value)
            return ()
        return question.options


def _date_fact(response: str, target: str) -> ParsedFact:
    """ISO in, ISO out; anything else is a clarification.

    Deliberately strict. A date is the one field where a near-miss reading is
    indistinguishable from a correct one at a glance — `04/09` is two different
    days depending on who wrote it — so an unparseable date stays unparsed and
    the patient is asked again.
    """
    from datetime import date

    raw = response.strip()
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return ParsedFact(
            slot=target,
            value=None,
            certainty=Certainty.UNCERTAIN,
            provenance=Provenance.SYSTEM_NORMALISED,
            evidence=raw or None,
        )
    return ParsedFact(
        slot=target,
        value=parsed.isoformat(),
        certainty=Certainty.CERTAIN,
        provenance=Provenance.PATIENT_REPORTED,
        evidence=raw,
    )


__all__ = ["Interpreter"]
