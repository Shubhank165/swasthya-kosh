"""Compile the engine's content into the bundle the phone walks offline.

The engine decides what to ask by scoring candidates against a patient's state,
which needs the state — and the state lives on the phone during the interview.
A Python engine reached over HTTP would give the app the adaptive selection and
take away the property that makes it work in an OPD with bad wifi, which
`docs/QUESTIONING_AGENT.md` flags as an open product decision. This file is the
third of the three ways out that document names: **precompile**.

What survives the compile and what does not is worth stating plainly, because
the difference is the whole cost of keeping the interview offline:

**Survives.** Every question, in all nine languages. Every prerequisite — a
question about sputum colour is still unreachable for a patient who never
mentioned a cough. Every red-flag rule. The runtime-filled options on "which of
these is worst". The clinical content stays authored in one place and reviewed
in one place.

**Does not.** Ranking. The engine asks the highest-scoring question given
everything known so far; the walker asks the applicable questions in a fixed
order. A patient answers the same set either way — `requires` decides the set,
not the score — but they answer it in a clinician-authored order rather than an
adaptive one. Also lost: the free-text parsers, which run server-side on the
submitted record instead of turning a sentence into slots as it is typed.

**The `*` rewrite is the safety-critical part of this file.** A general question
fills `<domain>.severity` for every active domain at once, so no question
extracts `fever.severity` and nothing on the phone would either. Two red-flag
rules read exactly that. Compiling them naively yields a bundle whose rules
reference fields nobody is ever asked — rules that cannot fire, and that look
like working safety coverage. `_FieldIndex` resolves those references onto the
general question that does fill them, and raises rather than emitting a rule
that reads a field no question produces.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.questioning_agent.core.enums import AnswerType
from app.questioning_agent.core.schemas import Condition, Question
from app.questioning_agent.knowledge.information_schema import ContentError, SlotRegistry
from app.questioning_agent.knowledge.questions import QuestionBank
from app.questioning_agent.localization.localization_loader import Localization
from app.questioning_agent.safety.triage import TriageRules

#: Bumped from the hand-authored bundle's "1": this one carries `options_from`,
#: and an app that ignores it renders "which of these is worst" with no options
#: at all. That is a shape an older build cannot read, which is what this
#: number is for.
BUNDLE_FORMAT_VERSION = "2"

#: The slot the fixed multi-select fills. Domain membership is read off it, so
#: it is the one field id this file hardcodes.
COMPLAINTS_FIELD = "routing.complaints"

#: Ordered, because the app shows "3 of 7 sections" and a set has no third.
SECTIONS = ("presenting", "symptoms", "history", "ayurveda")

#: The engine's answer types in the app's vocabulary. `structured_text` becomes
#: free text: the app renders a box and the interpreter pulls the slots out of
#: what was typed when the record reaches the backend, which is where those
#: parsers live.
_ANSWER_TYPES = {
    AnswerType.BOOLEAN: "yes_no_unknown",
    AnswerType.SINGLE_SELECT: "single_choice",
    AnswerType.MULTI_SELECT: "multi_choice",
    AnswerType.NUMERIC: "number",
    AnswerType.SCALE: "scale",
    AnswerType.DURATION: "duration",
    AnswerType.DATE: "date",
    AnswerType.FREE_TEXT: "free_text",
    AnswerType.STRUCTURED_TEXT: "free_text",
}


def _field_id(question: Question) -> str:
    """What the walker keys this question's answer by.

    A general question is keyed by its own id rather than by a slot, because the
    slot it fills has a `*` where a domain should be and there is one answer
    rather than one per domain. Everything else is keyed by the slot it fills,
    so a prerequisite naming that slot resolves without a lookup table.
    """
    if question.is_general:
        return question.id
    return question.extracts[0]


def _section(question: Question) -> str:
    if question.fixed_order is not None:
        return "presenting"
    if question.id.startswith("ayush."):
        return "ayurveda"
    if question.is_general or question.domains:
        return "symptoms"
    return "history"


#: Answer types whose recorded value is a code, a number or a date — something a
#: condition can be tested against. Free text is not one: the engine turns a
#: sentence into slots with parsers that do not exist on the phone, so on the
#: phone the answer is the sentence.
_EVALUABLE = frozenset(
    {
        AnswerType.BOOLEAN,
        AnswerType.SINGLE_SELECT,
        AnswerType.MULTI_SELECT,
        AnswerType.NUMERIC,
        AnswerType.SCALE,
        AnswerType.DATE,
        AnswerType.DURATION,
    }
)


class _FieldIndex:
    """Slot id to the field id of the question that fills it.

    Three cases, and the second is the one that matters:

    1. A question extracts the slot directly — `fever.measured`.
    2. Nothing extracts it, but a general question fills `*.<suffix>` and so
       fills this slot for every active domain — `fever.severity`. Resolves onto
       that question.
    3. `<domain>.present`, which no question extracts at all: it is set by the
       answer to the fixed multi-select, and is read as membership of it.

    **Several questions can fill one slot, and which one is chosen decides
    whether a red-flag rule works.** `pain.site` is filled both by a
    single-select asking where it hurts and by `pain.description`, a free-text
    box the interpreter pulls character, site, radiation and aggravating factors
    out of. Server-side both produce a coded site. On the phone the second
    produces a sentence, and `pain.site == chest` tested against a sentence is
    the cardiac rule silently never firing. So a question that asks for one slot
    and returns a code outranks one that asks for four and returns prose.
    """

    def __init__(self, bank: QuestionBank, slots: SlotRegistry) -> None:
        self._domains = {domain.id for domain in slots.domains}
        self._direct: dict[str, Question] = {}
        self._general: dict[str, Question] = {}

        for question in sorted(bank.all, key=lambda q: q.id):
            for slot in question.extracts:
                target = self._general if slot.startswith("*.") else self._direct
                key = slot[2:] if slot.startswith("*.") else slot
                if _better(question, target.get(key)):
                    target[key] = question

    def domain_of(self, slot: str) -> str | None:
        """The domain a `<domain>.present` slot refers to, or None."""
        domain, _, name = slot.partition(".")
        if name == "present" and domain in self._domains:
            return domain
        return None

    def source(self, slot: str) -> Question | None:
        direct = self._direct.get(slot)
        if direct is not None:
            return direct
        _, _, name = slot.partition(".")
        return self._general.get(name)

    def resolve(self, slot: str, *, why: str, evaluable: bool = False) -> str:
        question = self.source(slot)
        if question is None:
            raise ContentError(
                f"{why} reads slot {slot!r}, which no question fills. A condition "
                f"over a field nobody is asked can never be satisfied; in a "
                f"red-flag rule that is safety coverage which only appears to work."
            )
        if evaluable and question.answer_type not in _EVALUABLE:
            raise ContentError(
                f"{why} reads slot {slot!r}, which on the phone is filled only by "
                f"{question.id!r} — a {question.answer_type} question, whose "
                f"answer is a sentence rather than a value. The engine parses "
                f"that sentence into slots; the bundle has no parser, so the "
                f"criterion would compare a code against prose and never hold. "
                f"Give the slot a question that asks for it directly."
            )
        return _field_id(question)


def _better(question: Question, incumbent: Question | None) -> bool:
    """Whether `question` is a more reliable source for a slot than `incumbent`.

    Fewest slots first — a question asking for one thing returns that thing,
    where a four-slot free-text box returns a sentence somebody still has to
    read. Then evaluable answers over prose, then priority, then id so the
    bundle is byte-stable.
    """
    if incumbent is None:
        return True

    def rank(q: Question) -> tuple[int, int, int, str]:
        return (
            len(q.extracts),
            0 if q.answer_type in _EVALUABLE else 1,
            -q.priority,
            q.id,
        )

    return rank(question) < rank(incumbent)


def _condition(
    raw: Condition, index: _FieldIndex, *, why: str, evaluable: bool = False
) -> dict[str, Any]:
    """One prerequisite, in the app's expression language.

    The shapes line up almost exactly. The one that does not is
    `<domain>.present`: nothing fills it, because ticking a domain on the fixed
    question is what makes it true. It compiles to membership of that answer,
    which the walker already evaluates three-valued — unknown until the question
    is answered, which is what stops a domain's questions being ruled out before
    the patient has said what is wrong.
    """
    if raw.all:
        return {
            "all": [
                _condition(node, index, why=why, evaluable=evaluable) for node in raw.all
            ]
        }
    if raw.any:
        return {
            "any": [
                _condition(node, index, why=why, evaluable=evaluable) for node in raw.any
            ]
        }

    if raw.domain_active is not None:
        return {"field_id": COMPLAINTS_FIELD, "in": [raw.domain_active]}

    assert raw.slot is not None  # a Condition is a leaf or a branch; validated.
    domain = index.domain_of(raw.slot)
    if domain is not None:
        member: dict[str, Any] = {"field_id": COMPLAINTS_FIELD, "in": [domain]}
        # `present: false` is "the patient did not report this", which is the
        # negation of membership rather than a value of it.
        return member if raw.equals is not False else {"not": member}

    field = index.resolve(raw.slot, why=why, evaluable=evaluable)
    if raw.known is not None:
        return {"field_id": field, "status": "present" if raw.known else "absent"}
    if raw.any_of:
        return {"field_id": field, "in": list(raw.any_of)}
    return {"field_id": field, "equals": raw.equals}


def _question(
    question: Question, localization: Localization, index: _FieldIndex
) -> dict[str, Any]:
    prompts = {
        language: localization.question_text(question.id, language)
        for language in localization.languages
        if localization.has_question(question.id, language)
    }
    options = {
        option: {
            language: localization.option_text(option, language)
            for language in localization.languages
            if localization.has_option(option, language)
        }
        for option in question.options
    }

    body: dict[str, Any] = {
        "question_id": question.id,
        "field_id": _field_id(question),
        "section": _section(question),
        "answer_type": _ANSWER_TYPES[question.answer_type],
        "required": True,
        "prompts": prompts,
        "options": list(question.options) or None,
        # Option text, keyed the way prompts are. The hand-authored bundle put
        # option labels in the app's own strings; these are content, authored
        # per language beside the questions, and travel with them.
        "option_labels": options or None,
        "precondition": (
            _condition(question.requires, index, why=f"question {question.id!r}")
            if question.requires
            else None
        ),
        "allow_skip": True,
        "allow_unknown": True,
    }
    if question.options_from is not None:
        # The slot, resolved to the field the walker keys answers by, so the app
        # can read back what was ticked without knowing what a slot is.
        body["options_from"] = index.resolve(
            question.options_from, why=f"question {question.id!r} options_from"
        )
    for key, value in (
        ("unit", question.unit),
        ("units", list(question.units) or None),
        ("min", question.minimum),
        ("max", question.maximum),
    ):
        if value is not None:
            body[key] = value
    return body


def _plan(bank: QuestionBank) -> list[str]:
    """Every question, in the order the walker will offer the applicable ones.

    The engine would rank these per turn against what is already known. A fixed
    order cannot, so it is chosen to read like a consultation instead: what is
    wrong, then the things that apply to all of it, then each problem in turn,
    then the history every patient is asked for, then the AYUSH module.

    Within a group, priority descending and then id — descending because a
    question a case should not arrive without is worth asking before a patient
    tires of answering, and by id after that so the bundle is byte-stable.
    """

    def rank(question: Question) -> tuple[int, str]:
        return (-question.priority, question.id)

    fixed = sorted(
        (q for q in bank.all if q.fixed_order is not None),
        key=lambda q: q.fixed_order or 0,
    )
    adaptive = [q for q in bank.all if q.fixed_order is None]

    cross_domain = sorted((q for q in adaptive if q.is_general), key=rank)
    ayurveda = [q for q in adaptive if q.id.startswith("ayush.")]
    history = sorted(
        (
            q
            for q in adaptive
            if not q.is_general and not q.domains and not q.id.startswith("ayush.")
        ),
        key=rank,
    )

    per_domain: list[Question] = []
    domained = [q for q in adaptive if q.domains and not q.is_general]
    for domain in sorted({d for q in domained for d in q.domains}):
        per_domain.extend(
            sorted((q for q in domained if domain in q.domains), key=rank)
        )

    ordered = [*fixed, *cross_domain, *per_domain, *history]
    seen: set[str] = set()
    plan: list[str] = []
    for question in [*ordered, *ayurveda]:
        if question.id not in seen:
            seen.add(question.id)
            plan.append(question.id)
    return plan


def compile_bundle(
    *,
    bank: QuestionBank,
    slots: SlotRegistry,
    localization: Localization,
    triage: TriageRules,
    schema_version: str,
) -> dict[str, Any]:
    """The wire form.

    `branches` is empty and that is the point. The hand-authored bundle chose a
    limb from the one chief complaint, so a patient with fever *and* a cough was
    asked about one of them. Here every question carries its own prerequisite
    and the walker evaluates all of them, so a patient who ticks three problems
    is asked about three — which is what the engine does, and the reason the
    fixed question is a multi-select in the first place.
    """
    index = _FieldIndex(bank, slots)
    questions = sorted(bank.all, key=lambda q: q.id)
    plan = _plan(bank)
    ayurveda = [qid for qid in plan if qid.startswith("ayush.")]

    rules = [
        {
            "rule_id": rule.id,
            "severity": rule.severity,
            "criteria": {
                "all": [
                    _condition(
                        Condition(
                            slot=criterion.slot,
                            equals=criterion.equals,
                            any_of=criterion.any_of,
                        ),
                        index,
                        why=f"red-flag rule {rule.id!r}",
                        evaluable=True,
                    )
                    if criterion.at_least is None
                    else {
                        "field_id": index.resolve(
                            criterion.slot,
                            why=f"red-flag rule {rule.id!r}",
                            evaluable=True,
                        ),
                        "gte": criterion.at_least,
                    }
                    for criterion in rule.criteria
                ]
            },
        }
        for rule in triage.rules
    ]

    body: dict[str, Any] = {
        "bundle_format": BUNDLE_FORMAT_VERSION,
        "schema_version": schema_version,
        "languages": list(localization.languages),
        "sections": list(SECTIONS),
        "core": [qid for qid in plan if qid not in set(ayurveda)],
        # Nothing branches on the chief complaint any more — see the docstring.
        "branches": {},
        "ayurveda": ayurveda,
        # 2/3 §5 screen 8 — the full module on a first visit, this subset on a
        # return. A separate list rather than a flag per question because the
        # app chooses between two plans, and a plan is a list.
        "ayurveda_current_state": [
            qid for qid in ayurveda if bank.require(qid).current_state
        ],
        "questions": [_question(q, localization, index) for q in questions],
        "red_flag_rules": rules,
    }
    # Content-derived rather than a number somebody remembers to bump, and it
    # invalidates a resumed draft on exactly the edits that should: the walker
    # refuses to resume a draft whose content version has moved, because answers
    # recorded against questions that have since changed are answers nobody can
    # now read.
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    body["content_version"] = f"q1.{digest[:12]}"
    return body
