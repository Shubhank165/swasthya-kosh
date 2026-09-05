"""The question content bundle — 2/3 §3, §4.

The bundle is a contract between three parties: the Jetson that conducts the
spoken interview, the patient app that renders the touch form, and this backend
that compiles it. All three must agree on what a field id means, or the same id
arrives carrying two different questions' answers.

Most of what is asserted here is about what compilation must *never* do —
flatten a rule, drop a language, invent a type, or emit a rule that cannot fire.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.errors import ContentError
from app.domain.questions.bundle import canonical_json, compile_bundle, etag_for
from app.domain.questions.loader import load_questions
from app.domain.questions.model import AnswerType

QUESTIONS = Path(__file__).resolve().parents[3] / "clinical" / "questions"


@pytest.fixture(scope="module")
def question_set() -> Any:
    return load_questions(QUESTIONS, content_version="questions-test")


@pytest.fixture(scope="module")
def bundle(question_set: Any) -> dict[str, Any]:
    return compile_bundle(question_set, schema_version="0.1")


class TestItLoads:
    def test_the_shipped_content_compiles(self, bundle: dict[str, Any]) -> None:
        assert bundle["questions"]
        assert bundle["red_flag_rules"]
        assert bundle["branches"]

    def test_every_complaint_has_a_branch(
        self, question_set: Any, bundle: dict[str, Any]
    ) -> None:
        """A complaint a patient can choose with no branch behind it is a dead
        end: the app would ask the core questions and then stop."""
        complaint_question = next(
            q for q in question_set.core if q.field_id == "chief_complaint"
        )
        assert complaint_question.options is not None
        branchless = [
            option
            for option in complaint_question.options
            # `other` and `follow_up_visit` are handled by the general follow-up
            # pathway and by free text respectively.
            if option not in bundle["branches"] and option not in {"other", "follow_up_visit"}
        ]
        assert branchless == [], f"complaints with no questions behind them: {branchless}"

    def test_every_referenced_question_id_exists(self, bundle: dict[str, Any]) -> None:
        """`core`, `branches` and `ayurveda` are lists of ids into `questions`.

        A dangling id is a question the app is told to ask and has no text for.
        """
        known = {q["question_id"] for q in bundle["questions"]}
        referenced = set(bundle["core"]) | set(bundle["ayurveda"])
        for ids in bundle["branches"].values():
            referenced |= set(ids)
        assert referenced <= known, f"dangling: {sorted(referenced - known)}"


class TestTheAppCanRenderAllOfIt:
    def test_every_answer_type_is_one_the_app_knows(
        self, bundle: dict[str, Any]
    ) -> None:
        """§4 fixes the renderable set.

        An unknown type does not crash the app — it records `not_asked` and logs
        a version mismatch — which is the right degradation and the wrong
        outcome. A question silently unasked is a gap in a clinical history.
        """
        allowed = set(AnswerType.__args__)  # type: ignore[attr-defined]
        seen = {q["answer_type"] for q in bundle["questions"]}
        assert seen <= allowed, f"unrenderable: {sorted(seen - allowed)}"

    def test_every_choice_question_has_options(self, bundle: dict[str, Any]) -> None:
        for question in bundle["questions"]:
            if question["answer_type"] in {"single_choice", "multi_choice"}:
                assert question["options"], f"{question['question_id']} has no options"

    def test_every_question_offers_i_dont_know(self, bundle: dict[str, Any]) -> None:
        """Unconditional, by §4.

        A patient who cannot answer must always have a way to say so that is not
        a guess and not a silence — `unresolved`, never `no`.
        """
        assert all(q["allow_unknown"] for q in bundle["questions"])

    def test_consent_and_the_chief_complaint_cannot_be_skipped(
        self, bundle: dict[str, Any]
    ) -> None:
        """Everything else can. Without these two there is no intake to submit."""
        unskippable = {
            q["field_id"] for q in bundle["questions"] if not q["allow_skip"]
        }
        assert {"consent_given", "chief_complaint"} <= unskippable


class TestLanguages:
    def test_every_question_has_every_advertised_language(
        self, bundle: dict[str, Any]
    ) -> None:
        """The loader is fatal on a missing prompt, so this is a regression
        guard rather than a discovery.

        No English fallback: a patient answering a question in a language they
        did not choose produces a record saying they answered something they may
        not have understood.
        """
        for question in bundle["questions"]:
            for language in bundle["languages"]:
                assert question["prompts"].get(language), (
                    f"{question['question_id']} has no {language} prompt"
                )

    def test_it_advertises_only_what_is_authored(self, bundle: dict[str, Any]) -> None:
        """Two languages, because two are written.

        2/3 §14 asks for nine locales of *UI chrome*, which is a different
        artefact and may be an engineering draft. Clinical prompts are not:
        machine-translating a question silently changes what the record means,
        and §16 forbids inventing question content.
        """
        assert bundle["languages"] == ["en", "hi"]

    def test_a_language_with_no_prompts_is_refused(self) -> None:
        with pytest.raises(ContentError, match="no prompt"):
            load_questions(QUESTIONS, content_version="x", languages=("en", "ta"))


class TestRedFlagRules:
    def test_nesting_survives_compilation(self, bundle: dict[str, Any]) -> None:
        """The cardiac rule is `chest pain AND sudden AND (dyspnoea OR sweat)`.

        §4's example shows a flat `all` list. Flattening this one would turn the
        disjunction into a conjunction and require both symptoms — a strictly
        narrower rule, on the criterion that exists to catch a myocardial
        infarction in a waiting room.
        """
        rule = next(
            r for r in bundle["red_flag_rules"]
            if r["rule_id"] == "acute_chest_pain_with_dyspnoea"
        )
        assert "any" in json.dumps(rule)

    def test_complaint_concepts_are_resolved_to_a_real_field(
        self, bundle: dict[str, Any]
    ) -> None:
        """Rules were authored against `{concept: chest_pain, status: present}`.

        Nothing asks a question called `chest_pain`; the previous engine made
        choosing a complaint assert a concept of the same name. Read literally
        every complaint-gated rule was unfirable. They are rewritten at compile
        time into a test on `chief_complaint`, so a walker that knows nothing
        can evaluate them — rather than each of three clients reimplementing the
        implication.
        """
        rule = next(
            r for r in bundle["red_flag_rules"] if r["rule_id"] == "thunderclap_headache"
        )
        leaves = rule["criteria"]["all"]
        assert {"field_id": "chief_complaint", "in": ["headache"]} in leaves

    def test_no_rule_reads_a_field_nothing_asks(self, question_set: Any) -> None:
        """Enforced by the loader; asserted here because it is the property that
        makes the rules real. A rule reading an unasked field can never fire and
        is indistinguishable from working safety coverage."""
        asked = {q.field_id for q in question_set.all_questions()}
        for rule in question_set.red_flags:
            assert rule.criteria.fields_read() <= asked, rule.rule_id

    def test_no_rule_needs_two_chief_complaints_at_once(
        self, question_set: Any
    ) -> None:
        """The failure mode the complaint rewrite could have introduced.

        The meningitis rule reads a headache and a fever. Had its fever leaf
        been the complaint `fever` rather than the screen question
        `associated_fever`, the rewrite would have produced "the chief complaint
        is both headache and fever" — never true, and silently so.
        """
        def complaint_sets(node: Any) -> list[frozenset[str]]:
            if node.all_ is not None:
                found: list[frozenset[str]] = []
                for child in node.all_:
                    found.extend(complaint_sets(child))
                return found
            if node.field_id == "chief_complaint" and node.in_ is not None:
                return [frozenset(node.in_)]
            return []

        for rule in question_set.red_flags:
            sets = complaint_sets(rule.criteria)
            if len(sets) > 1:
                assert frozenset.intersection(*sets), rule.rule_id

    def test_the_meningitis_rule_can_fire(self, question_set: Any) -> None:
        """Named explicitly, because it is the one the rewrite endangered."""
        rule = next(
            r for r in question_set.red_flags
            if r.rule_id == "headache_with_fever_and_neck_stiffness"
        )
        assert rule.criteria.fields_read() == {
            "chief_complaint", "associated_fever", "neck_stiffness"
        }

    def test_every_rule_is_sourced(self, question_set: Any) -> None:
        """An unsourced rule does not load. Asserted so the loader's guard is
        not quietly relaxed."""
        assert all(r.clinical_source.strip() for r in question_set.red_flags)

    def test_no_rule_label_names_a_condition(self, question_set: Any) -> None:
        """A red flag says a human must look now. It never says what is wrong.

        The app's urgent-care screen has its own bounded wording and does not
        render these, but a label that named a condition would still reach a
        physician's dashboard and, eventually, a patient's screen.
        """
        forbidden = {
            "infarction", "myocardial", "meningitis", "sepsis", "stroke", "embolism",
            "appendicitis", "perforation", "dengue", "malaria", "cancer",
        }
        for rule in question_set.red_flags:
            words = set(rule.label.lower().replace(",", " ").split())
            assert not (words & forbidden), f"{rule.rule_id}: {rule.label!r}"


class TestTheWireForm:
    def test_it_is_byte_stable(self, question_set: Any) -> None:
        """The ETag is a hash of the body.

        A bundle that differed between two identical compilations would change
        its own ETag on every request, and every client would re-download 80 KB
        on every launch — defeating the 304 entirely.
        """
        first = canonical_json(compile_bundle(question_set, schema_version="0.1"))
        second = canonical_json(compile_bundle(question_set, schema_version="0.1"))
        assert first == second
        assert etag_for(json.loads(first)) == etag_for(json.loads(second))

    def test_the_etag_changes_when_the_content_does(self, question_set: Any) -> None:
        """Content-derived, not version-derived, so an edit somebody forgot to
        bump `content_version` for still invalidates every cached copy."""
        base = compile_bundle(question_set, schema_version="0.1")
        edited = json.loads(canonical_json(base))
        edited["questions"][0]["prompts"]["en"] = "changed"
        assert etag_for(base) != etag_for(edited)

    def test_devanagari_travels_as_utf8_not_escapes(self, bundle: dict[str, Any]) -> None:
        """A third smaller on the wire, on what may be a patient's mobile data."""
        assert "\\u" not in canonical_json(bundle)

    def test_it_names_the_record_contract_it_produces(
        self, bundle: dict[str, Any]
    ) -> None:
        """An app that cannot produce this schema version must refuse to start
        an intake rather than attempt partial compatibility (§4)."""
        assert bundle["schema_version"] == "0.1"
