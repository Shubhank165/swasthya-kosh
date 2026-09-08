"""The bundle the phone walks offline — `questioning_agent/output/bundle.py`.

The engine's own tests are conversations: they hand it a state and check what it
asks next. These are not. What is checked here is that the *compiled* form keeps
the properties the engine has, because the phone runs the compiled form and
nobody on the phone can ask the engine anything.

The red-flag tests are the ones that matter. A rule compiled onto a field no
question fills, or onto a free-text box, is a rule that cannot fire — and a
questionnaire with safety coverage that cannot fire is worse than one with none,
because the first looks like it works.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.questioning_agent.knowledge.information_schema import ContentError, SlotRegistry
from app.questioning_agent.knowledge.questions import QuestionBank
from app.questioning_agent.localization.localization_loader import Localization
from app.questioning_agent.output.bundle import compile_bundle
from app.questioning_agent.safety.triage import TriageRules
from tests.questioning.conftest import CONTENT

#: Answer types whose value is text rather than something a condition can test.
UNEVALUABLE = {"free_text"}


@pytest.fixture(scope="module")
def bundle() -> dict[str, Any]:
    slots = SlotRegistry.load(CONTENT)
    return compile_bundle(
        bank=QuestionBank.load(CONTENT, slots),
        slots=slots,
        localization=Localization.load(CONTENT),
        triage=TriageRules.load(CONTENT),
        schema_version="0.2",
    )


def leaves(condition: dict[str, Any]) -> list[dict[str, Any]]:
    if "all" in condition:
        return [leaf for node in condition["all"] for leaf in leaves(node)]
    if "any" in condition:
        return [leaf for node in condition["any"] for leaf in leaves(node)]
    if "not" in condition:
        return leaves(condition["not"])
    return [condition]


class TestEveryConditionCanBeEvaluated:
    """A condition over a field nobody is asked is one that never holds."""

    def test_every_field_a_condition_reads_is_one_a_question_fills(
        self, bundle: dict[str, Any]
    ) -> None:
        fields = {q["field_id"] for q in bundle["questions"]}
        read = {
            leaf["field_id"]
            for rule in bundle["red_flag_rules"]
            for leaf in leaves(rule["criteria"])
        } | {
            leaf["field_id"]
            for question in bundle["questions"]
            if question["precondition"]
            for leaf in leaves(question["precondition"])
        }
        assert read <= fields

    def test_no_red_flag_rule_reads_a_free_text_answer(
        self, bundle: dict[str, Any]
    ) -> None:
        """The one that caught a real defect.

        `pain.site` is filled by a single-select asking where it hurts *and* by
        `pain.description`, a free-text box the interpreter pulls four slots out
        of. The compiler first resolved onto the second, so the cardiac rule
        compared `chest` against a sentence and could never fire.
        """
        types = {q["field_id"]: q["answer_type"] for q in bundle["questions"]}
        for rule in bundle["red_flag_rules"]:
            for leaf in leaves(rule["criteria"]):
                assert types[leaf["field_id"]] not in UNEVALUABLE, (
                    f"{rule['rule_id']} reads {leaf['field_id']}, which is free "
                    f"text on the phone"
                )

    def test_the_cardiac_rule_reads_the_coded_site_and_onset(
        self, bundle: dict[str, Any]
    ) -> None:
        """Named explicitly because it is the rule the interview exists to catch."""
        rule = next(
            r for r in bundle["red_flag_rules"] if r["rule_id"] == "chest_pain_sudden_onset"
        )
        read = {leaf["field_id"]: leaf for leaf in leaves(rule["criteria"])}
        assert read["pain.site"]["equals"] == "chest"
        assert read["general.onset"]["equals"] == "sudden"
        assert read["routing.complaints"]["in"] == ["pain"]


class TestTheGeneralQuestionRewrite:
    """`*.severity` fills `fever.severity`, and no question extracts that."""

    def test_a_severity_rule_resolves_onto_the_question_that_asks_it(
        self, bundle: dict[str, Any]
    ) -> None:
        rule = next(
            r for r in bundle["red_flag_rules"] if r["rule_id"] == "high_fever_prolonged"
        )
        read = {leaf["field_id"]: leaf for leaf in leaves(rule["criteria"])}
        # Not `fever.severity`: one question asks how bad things are, once, for
        # every domain the patient ticked.
        assert read["general.severity"]["gte"] == 8

    def test_a_rule_reading_a_slot_nothing_fills_is_refused(self) -> None:
        slots = SlotRegistry.load(CONTENT)
        bank = QuestionBank.load(CONTENT, slots)
        from app.questioning_agent.safety.triage import Criterion, Rule
        from app.questioning_agent.safety.triage import TriageRules as T

        invented = T(
            (
                Rule(
                    id="invented",
                    severity="high",
                    label="Urgent clinical review criterion triggered",
                    criteria=(Criterion(slot="fever.no_such_slot", equals=True),),
                ),
            )
        )
        with pytest.raises(ContentError, match="no question fills"):
            compile_bundle(
                bank=bank,
                slots=slots,
                localization=Localization.load(CONTENT),
                triage=invented,
                schema_version="0.2",
            )


class TestDomainsGateTheQuestions:
    def test_a_domain_question_hangs_off_membership_of_the_fixed_answer(
        self, bundle: dict[str, Any]
    ) -> None:
        """`fever.present` is not a field. Ticking fever on question 1 is."""
        question = next(
            q for q in bundle["questions"] if q["question_id"] == "fever.measured"
        )
        assert question["precondition"] == {
            "field_id": "routing.complaints",
            "in": ["fever"],
        }

    def test_nothing_branches_on_the_chief_complaint(
        self, bundle: dict[str, Any]
    ) -> None:
        """A patient who ticks three problems is asked about three.

        The hand-authored bundle chose one limb from the single chief complaint,
        so the other two went unasked. Every question carrying its own
        prerequisite is what replaces that.
        """
        assert bundle["branches"] == {}


class TestTheRuntimeFilledQuestion:
    def test_which_is_worst_offers_back_what_was_ticked(
        self, bundle: dict[str, Any]
    ) -> None:
        question = next(
            q for q in bundle["questions"] if q["question_id"] == "fixed.chief_complaint"
        )
        assert question["options_from"] == "routing.complaints"
        assert question["options"] is None


class TestEveryQuestionIsRenderable:
    def test_every_question_carries_text_in_every_advertised_language(
        self, bundle: dict[str, Any]
    ) -> None:
        for question in bundle["questions"]:
            missing = set(bundle["languages"]) - set(question["prompts"])
            assert not missing, f"{question['question_id']} has no text in {missing}"

    def test_every_option_carries_text_in_every_advertised_language(
        self, bundle: dict[str, Any]
    ) -> None:
        for question in bundle["questions"]:
            for option, labels in (question["option_labels"] or {}).items():
                missing = set(bundle["languages"]) - set(labels)
                assert not missing, f"option {option!r} has no text in {missing}"

    def test_the_app_can_render_every_answer_type(
        self, bundle: dict[str, Any]
    ) -> None:
        """§4 lets an unknown type degrade to `not_asked`. None should be.

        `structured_text` is deliberately absent: it is compiled to free text,
        because the parsers that make it structured run on the backend.
        """
        renderable = {
            "single_choice",
            "multi_choice",
            "yes_no_unknown",
            "number",
            "scale",
            "duration",
            "date",
            "free_text",
        }
        assert {q["answer_type"] for q in bundle["questions"]} <= renderable

    def test_every_question_in_the_plan_exists(self, bundle: dict[str, Any]) -> None:
        known = {q["question_id"] for q in bundle["questions"]}
        planned = [*bundle["core"], *bundle["ayurveda"]]
        assert set(planned) <= known
        assert len(planned) == len(set(planned)), "a question is planned twice"
        assert set(planned) == known, "a question exists but is never planned"

    def test_the_return_visit_subset_is_a_subset(self, bundle: dict[str, Any]) -> None:
        subset = set(bundle["ayurveda_current_state"])
        assert subset
        assert subset < set(bundle["ayurveda"])


class TestTheFixedThreeComeFirst:
    def test_the_plan_opens_with_them_in_order(self, bundle: dict[str, Any]) -> None:
        assert bundle["core"][:3] == [
            "fixed.complaints",
            "fixed.chief_complaint",
            "fixed.timeline",
        ]


class TestItIsByteStable:
    def test_two_compiles_of_one_content_set_are_identical(self) -> None:
        """The ETag is a hash of the body; an unstable bundle defeats the 304."""
        slots = SlotRegistry.load(CONTENT)
        args = dict(
            bank=QuestionBank.load(CONTENT, slots),
            slots=slots,
            localization=Localization.load(CONTENT),
            triage=TriageRules.load(CONTENT),
            schema_version="0.2",
        )
        first = compile_bundle(**args)  # type: ignore[arg-type]
        second = compile_bundle(**args)  # type: ignore[arg-type]
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


class TestTheAppFixtureIsCurrent:
    """The committed fixture the Dart walker tests walk.

    Checked in because the app's test suite must not need a Python toolchain to
    run, and guarded here because a fixture nobody regenerates is a test that
    passes against content the app no longer receives.
    """

    def test_it_matches_what_the_backend_would_serve(
        self, bundle: dict[str, Any]
    ) -> None:
        fixture = Path(__file__).resolve().parents[2].parent / (
            "app/test/fixtures/questioning_bundle.json"
        )
        assert fixture.is_file(), f"missing: {fixture}"
        committed = json.loads(fixture.read_text(encoding="utf-8"))
        assert committed == bundle, (
            "the app's bundle fixture is stale. Regenerate it:\n"
            "  backend/./.venv/bin/python -m scripts.dump_bundle"
        )
