"""Parse the authored question YAML into a `QuestionSet` — 2/3 §4.

Strict, and fatal on anything it cannot parse. The same reasoning the clinical
content loader already uses: a pathway that does not parse must stop the process,
because a system that quietly serves a bundle with a missing red-flag screen
looks exactly like a working one.

The authored vocabulary and the bundle vocabulary differ, and this is the only
place that knows both. Content authors write `concept`, `skippable` and
`answer: {type: quantity, unit: years}`; the bundle carries `field_id`,
`allow_skip` and `answer_type: number`. Translating here means a content author
never has to think about the wire format, and the app never has to know what a
Vaidya's YAML looks like.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from app.core.errors import ContentError
from app.domain.questions.model import (
    TYPE_ALIASES,
    AnswerType,
    Condition,
    Question,
    QuestionSet,
    RedFlagRule,
)

#: Section order as a physician reads a history. The bundle carries this so the
#: app's progress indicator — "3 of 7 sections", never a percentage — and the
#: report agree on what a section is and what order they come in.
SECTION_ORDER: tuple[str, ...] = (
    "identity",
    "consent",
    "chief_complaint",
    "hpi",
    "red_flag_screen",
    "review_of_systems",
    "past_medical",
    "past_surgical",
    "medications",
    "allergies",
    "family_history",
    "personal_history",
    "ayurveda",
    "documents",
    "confirmation",
)


def _read(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentError(f"{path.name} is not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ContentError(f"{path.name} must be a mapping at the top level")
    return loaded


def _condition(raw: Mapping[str, Any] | None) -> Condition | None:
    """Authored criteria into the shared expression type.

    Authors write `concept`; the wire says `field_id`. Renaming here rather than
    in the YAML keeps every stored record, every red-flag rule and every
    reviewer's mental model on the word `concept`.
    """
    if raw is None:
        return None
    body = dict(raw)
    for combinator in ("all", "any"):
        if combinator in body:
            body[combinator] = [_condition(c) for c in body[combinator]]
    if "not" in body:
        body["not"] = _condition(body["not"])
    if "concept" in body:
        body["field_id"] = body.pop("concept")
    return Condition.model_validate(body)


def _answer_type(raw: str, source: str, concept: str) -> AnswerType:
    resolved = TYPE_ALIASES.get(raw, raw)
    if resolved not in AnswerType.__args__:  # type: ignore[attr-defined]
        raise ContentError(
            f"{source}: field {concept!r} has answer type {raw!r}, which the app "
            f"cannot render. Add it to TYPE_ALIASES or use one of "
            f"{sorted(AnswerType.__args__)}"  # type: ignore[attr-defined]
        )
    return resolved  # type: ignore[return-value]


def _question(
    raw: Mapping[str, Any],
    *,
    source: str,
    default_section: str,
    languages: Sequence[str],
) -> Question:
    concept = raw.get("concept")
    if not concept:
        raise ContentError(f"{source}: a field has no `concept`")
    answer = raw.get("answer") or {}
    prompts = raw.get("prompts") or {}

    # A missing prompt is fatal rather than falling back to English. A patient
    # answering a question in a language they did not choose — because the
    # translation was never written — produces a record that says they answered
    # something they may not have understood.
    missing = [lang for lang in languages if not prompts.get(lang)]
    if missing:
        raise ContentError(
            f"{source}: field {concept!r} has no prompt for {missing}. "
            f"Every field needs a prompt in every advertised language."
        )

    return Question(
        question_id=f"{source}.{concept}",
        field_id=str(concept),
        section=str(raw.get("section") or default_section),
        answer_type=_answer_type(str(answer.get("type", "")), source, str(concept)),
        options=tuple(answer["options"]) if answer.get("options") else None,
        unit=answer.get("unit"),
        minimum=answer.get("min"),
        maximum=answer.get("max"),
        prompts={lang: str(prompts[lang]) for lang in languages},
        required=bool(raw.get("required", True)),
        # `skippable` defaults true in the authored content; the two fields that
        # set it false are consent and the chief complaint, without which there
        # is no intake to submit.
        allow_skip=bool(raw.get("skippable", True)),
        precondition=_condition(raw.get("precondition")),
        priority=int(raw.get("priority", 0)),
        needs_clinical_review=bool(raw.get("needs_clinical_review", False)),
        current_state=bool(raw.get("current_state", False)),
    )


def _questions_from(
    path: Path, *, default_section: str, languages: Sequence[str]
) -> tuple[Question, ...]:
    document = _read(path)
    source = str(document.get("id") or path.stem)
    section = str(document.get("section") or default_section)
    fields = document.get("fields") or []
    parsed = [
        _question(f, source=source, default_section=section, languages=languages)
        for f in fields
    ]
    # Authored order is by `priority` within a section; the walker takes the
    # order it is given and does not re-sort, so it is sorted once, here.
    parsed.sort(key=lambda q: (SECTION_ORDER.index(q.section)
                               if q.section in SECTION_ORDER else len(SECTION_ORDER),
                               q.priority))
    return tuple(parsed)


def load_questions(
    directory: Path, *, content_version: str, languages: Sequence[str] = ("en", "hi")
) -> QuestionSet:
    """Everything under `clinical/questions/`, parsed and cross-checked."""
    pathways = directory / "pathways"
    if not pathways.is_dir():
        raise ContentError(f"no question pathways at {pathways}")

    core = _questions_from(
        pathways / "core_intake.yaml", default_section="hpi", languages=languages
    )

    ros: dict[str, tuple[Question, ...]] = {}
    for path in sorted((pathways / "ros").glob("*.yaml")):
        ros[path.stem] = _questions_from(
            path, default_section="review_of_systems", languages=languages
        )

    screens: dict[str, tuple[Question, ...]] = {}
    for path in sorted((pathways / "screens").glob("*.yaml")):
        screens[path.stem] = _questions_from(
            path, default_section="red_flag_screen", languages=languages
        )

    branches: dict[str, tuple[Question, ...]] = {}
    for path in sorted(pathways.glob("*.yaml")):
        if path.name == "core_intake.yaml":
            continue
        document = _read(path)
        complaint = str(document.get("id") or path.stem)
        questions = list(
            _questions_from(path, default_section="hpi", languages=languages)
        )
        # A complaint's screen is part of that complaint's branch, not a
        # separate thing the app has to know to fetch. The screen questions are
        # what the red-flag rules read, so a branch without its screen is a
        # branch whose rules can never fire.
        questions.extend(screens.get(complaint, ()))
        for group in document.get("review_of_systems") or []:
            questions.extend(ros.get(str(group), ()))
        questions.extend(screens.get("general", ()))
        branches[complaint] = tuple(questions)

    ayurveda: tuple[Question, ...] = ()
    ayurveda_dir = directory / "ayurveda"
    if ayurveda_dir.is_dir():
        for path in sorted(ayurveda_dir.glob("*.yaml")):
            ayurveda = ayurveda + _questions_from(
                path, default_section="ayurveda", languages=languages
            )

    complaints = _complaint_values(core)

    red_flags: list[RedFlagRule] = []
    for path in sorted((directory / "redflags").glob("*.yaml")):
        document = _read(path)
        for raw in document.get("rules") or []:
            criteria = _condition(raw.get("criteria"))
            if criteria is None:
                raise ContentError(f"{path.name}: rule {raw.get('id')!r} has no criteria")
            criteria = _resolve_complaints(criteria, complaints, rule=str(raw["id"]))
            red_flags.append(
                RedFlagRule(
                    rule_id=str(raw["id"]),
                    severity=str(raw.get("severity", "high")),
                    label=str(raw.get("label", "")),
                    criteria=criteria,
                    clinical_source=str(raw.get("clinical_source", "")),
                    guidance=raw.get("guidance"),
                )
            )

    question_set = QuestionSet(
        content_version=content_version,
        languages=tuple(languages),
        core=core,
        branches=branches,
        ayurveda=ayurveda,
        red_flags=tuple(red_flags),
        sections=tuple(
            s for s in SECTION_ORDER
            if any(q.section == s for q in _every(core, branches, ayurveda))
        ),
    )
    _check_rules_are_answerable(question_set)
    _check_no_rule_is_unsatisfiable(question_set)
    return question_set



def _complaint_values(core: Sequence[Question]) -> frozenset[str]:
    """The options of `chief_complaint`, which double as concept names."""
    for question in core:
        if question.field_id == "chief_complaint" and question.options:
            return frozenset(question.options)
    raise ContentError("core_intake has no `chief_complaint` field with options")


def _resolve_complaints(
    condition: Condition, complaints: frozenset[str], *, rule: str
) -> Condition:
    """Rewrite `{concept: chest_pain, status: present}` into a readable test.

    The previous engine held facts keyed by concept, so selecting `chest_pain`
    as the chief complaint made the *concept* `chest_pain` present, and the
    red-flag rules were written against that. Nothing asks a question called
    `chest_pain`, so read literally these rules can never fire — which the
    answerability check below proves.

    The fix is not to teach the app that answering one question asserts a
    different field: that is clinical logic, and `2/3 §16` forbids a second
    implementation of it in Dart. It is to say what the rule means, once, here:
    `chief_complaint is chest_pain`. The rewritten rule is what the Jetson and
    the app both receive, and it is evaluable by a walker that knows nothing.

    Only `status: present` is rewritten. Anything else on a complaint leaf is an
    assumption this function has not checked, so it raises rather than guessing.
    """
    if condition.all_ is not None:
        return condition.model_copy(update={
            "all_": tuple(_resolve_complaints(c, complaints, rule=rule)
                          for c in condition.all_)
        })
    if condition.any_ is not None:
        return condition.model_copy(update={
            "any_": tuple(_resolve_complaints(c, complaints, rule=rule)
                          for c in condition.any_)
        })
    if condition.not_ is not None:
        return condition.model_copy(update={
            "not_": _resolve_complaints(condition.not_, complaints, rule=rule)
        })
    if condition.field_id in complaints:
        if condition.status != "present":
            raise ContentError(
                f"rule {rule!r} tests complaint {condition.field_id!r} with "
                f"status {condition.status!r}. Only `present` has a defined "
                f"meaning as a chief complaint."
            )
        return Condition(field_id="chief_complaint", **{"in": (condition.field_id,)})
    return condition



def _check_no_rule_is_unsatisfiable(question_set: QuestionSet) -> None:
    """No rule may require the chief complaint to be two things at once.

    `_resolve_complaints` turns a complaint concept into a test on
    `chief_complaint`, and a patient has exactly one. So a rule that ANDs two
    different complaint tests can never fire — and would look like safety
    coverage while being dead.

    This is not hypothetical: the meningitis rule reads `headache` and a fever,
    and had the fever leaf been the complaint `fever` rather than the screen
    question `associated_fever`, the rewrite would have quietly disabled it.
    """
    def complaint_sets(node: Condition) -> list[frozenset[str]]:
        if node.all_ is not None:
            found: list[frozenset[str]] = []
            for child in node.all_:
                found.extend(complaint_sets(child))
            return found
        if node.field_id == "chief_complaint" and node.in_ is not None:
            return [frozenset(node.in_)]
        return []

    dead: dict[str, list[list[str]]] = {}
    for rule in question_set.red_flags:
        sets = complaint_sets(rule.criteria)
        if len(sets) > 1:
            intersection = frozenset.intersection(*sets)
            if not intersection:
                dead[rule.rule_id] = [sorted(s) for s in sets]
    if dead:
        raise ContentError(
            "red-flag rules require the chief complaint to be two different "
            f"things at once, so they can never fire: {dead}"
        )


def _every(
    core: Sequence[Question],
    branches: Mapping[str, Sequence[Question]],
    ayurveda: Sequence[Question],
) -> list[Question]:
    out = list(core) + list(ayurveda)
    for group in branches.values():
        out.extend(group)
    return out


def _check_rules_are_answerable(question_set: QuestionSet) -> None:
    """Every red-flag rule must read fields something actually asks.

    A rule reading a field no question collects can never fire, and is
    indistinguishable from working safety coverage until the day it was needed.
    This is the check that catches a screen being renamed out from under its
    rules.
    """
    asked = {q.field_id for q in question_set.all_questions()}
    unanswerable: dict[str, list[str]] = {}
    for rule in question_set.red_flags:
        missing = sorted(rule.criteria.fields_read() - asked)
        if missing:
            unanswerable[rule.rule_id] = missing
    if unanswerable:
        raise ContentError(
            "red-flag rules read fields that no question asks, so they can never "
            f"fire: {unanswerable}"
        )
