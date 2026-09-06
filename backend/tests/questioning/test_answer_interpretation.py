"""What the parsers make of what a patient wrote — §31.

The negation tests are the ones that matter most and they are mandatory (§16).
`"I don't have a fever"` becoming `fever.present = True` is not a parsing bug —
it is a symptom in a clinical record that the patient explicitly denied, and
nothing downstream can tell it from one they reported.
"""

from __future__ import annotations

import pytest

from app.questioning_agent.core.enums import Certainty
from app.questioning_agent.interpretation.boolean_parser import parse_boolean
from app.questioning_agent.interpretation.duration_parser import find_duration
from app.questioning_agent.interpretation.free_text_parser import parse_free_text
from app.questioning_agent.interpretation.numeric_parser import parse_numeric
from app.questioning_agent.interpretation.option_parser import (
    parse_multi_select,
    parse_single_select,
)


class TestYesAndNo:
    @pytest.mark.parametrize(
        "text",
        ["yes", "Yes", "yeah", "yep", "haan", "correct", "definitely", "ok"],
    )
    def test_an_affirmation_is_true(self, text: str, english) -> None:
        assert parse_boolean(text, "fever.present", english).value is True

    @pytest.mark.parametrize("text", ["no", "nope", "nah", "nahi", "none"])
    def test_a_denial_is_false(self, text: str, english) -> None:
        assert parse_boolean(text, "fever.present", english).value is False

    def test_a_sentence_carrying_a_yes(self, english) -> None:
        fact = parse_boolean(
            "Yeah, I've been running a temperature since yesterday.",
            "fever.present",
            english,
        )
        assert fact.value is True
        assert fact.certainty is Certainty.CERTAIN


class TestNegation:
    """§16. Mandatory, and the reason the parser has a scope rather than a flag."""

    @pytest.mark.parametrize(
        "text",
        [
            "I don't have a fever",
            "no fever",
            "I haven't had fever recently",
            "not really, no fever at all",
            "never had a fever",
        ],
    )
    def test_a_denied_symptom_is_never_present(self, text: str, english) -> None:
        fact = parse_boolean(text, "fever.present", english)
        assert fact.value is not True, f"{text!r} became present"

    def test_a_boundary_ends_the_scope(self, english) -> None:
        """"No fever **but** a bad cough" — the cough is not negated."""
        facts = parse_free_text(
            "no fever but a burning pain",
            ("pain.character",),
            _slots(),
            english,
        )
        assert [f.value for f in facts] == ["burning"]

    def test_a_negated_option_does_not_match(self, english) -> None:
        fact = parse_single_select(
            "not burning, more of a dull ache",
            "pain.character",
            ("burning", "dull_ache", "cramping"),
            english,
        )
        assert fact.value == "dull_ache"

    def test_hindi_negates_at_the_end_of_the_clause(self, hindi) -> None:
        """The reason each language has its own rules.

        Hindi puts `नहीं` after the noun it negates, so a parser that scanned
        only backwards — which is correct for English — would read this denial
        as an affirmation.
        """
        assert parse_boolean("बुखार नहीं है", "fever.present", hindi).value is False
        assert parse_boolean("हाँ, बुखार है", "fever.present", hindi).value is True


class TestUncertainty:
    """§19. An answer the parser cannot read does not become an answer."""

    @pytest.mark.parametrize("text", ["I think maybe", "not sure", "perhaps", "hmm"])
    def test_a_hedge_is_not_a_yes(self, text: str, english) -> None:
        fact = parse_boolean(text, "fever.present", english)
        assert fact.value is not True

    def test_nonsense_is_uncertain_rather_than_no(self, english) -> None:
        """The distinction the five statuses exist for.

        "asdkjh" is not a denial. Recording one would put a negative finding in
        the record on the strength of a typo.
        """
        fact = parse_boolean("asdkjh", "fever.present", english)
        assert fact.certainty is Certainty.UNCERTAIN
        assert fact.usable is False

    def test_maybe_yes_is_probable_not_certain(self, english) -> None:
        fact = parse_boolean("maybe yes", "fever.present", english)
        assert fact.value is True
        assert fact.certainty is Certainty.PROBABLE


class TestDurations:
    @pytest.mark.parametrize(
        ("text", "value", "unit", "approximate"),
        [
            ("three days", 3, "day", False),
            ("3 days", 3, "day", False),
            ("about a week", 1, "week", True),
            ("for the last 4-5 days", 4, "day", True),
            ("two weeks", 2, "week", False),
            ("since yesterday", 1, "day", False),
            ("6 months", 6, "month", False),
        ],
    )
    def test_it_reads_a_length_of_time(
        self, text: str, value: float, unit: str, approximate: bool, english
    ) -> None:
        duration = find_duration(text, english)
        assert duration is not None, text
        assert (duration.value, duration.unit) == (value, unit)
        assert duration.approximate is approximate

    def test_a_range_takes_the_lower_bound_and_says_it_is_approximate(
        self, english
    ) -> None:
        """"4 or 5 days" is a patient saying they do not know.

        4.5 would be a number nobody said, carrying a precision nobody has.
        """
        duration = find_duration("4 or 5 days", english)
        assert duration is not None
        assert duration.value == 4
        assert duration.approximate is True

    def test_comes_and_goes_is_not_a_duration(self, english) -> None:
        """It is a pattern, and guessing a length from it would invent one."""
        assert find_duration("it comes and goes", english) is None

    def test_hindi_durations(self, hindi) -> None:
        duration = find_duration("तीन दिन से", hindi)
        assert duration is not None
        assert (duration.value, duration.unit) == (3, "day")


class TestNumbers:
    @pytest.mark.parametrize(
        ("text", "value", "unit"),
        [
            ("102", 102, "fahrenheit"),
            ("102 F", 102, "fahrenheit"),
            ("102°F", 102, "fahrenheit"),
            ("39 C", 39, "celsius"),
            ("39°C", 39, "celsius"),
            ("about 102", 102, "fahrenheit"),
        ],
    )
    def test_temperatures(self, text: str, value: float, unit: str, english) -> None:
        fact = parse_numeric(
            text,
            "fever.maximum_temperature",
            english,
            unit="fahrenheit",
            units=("fahrenheit", "celsius"),
            minimum=30,
            maximum=110,
        )
        assert fact.value == {"value": value, "unit": unit}

    def test_nothing_is_converted(self, english) -> None:
        """102 °F stays 102. 38.9 is a figure the patient never said."""
        fact = parse_numeric(
            "102 F",
            "fever.maximum_temperature",
            english,
            unit="fahrenheit",
            units=("fahrenheit", "celsius"),
        )
        assert fact.value["value"] == 102

    def test_an_unmarked_unit_is_inferred_but_marked_as_inferred(self, english) -> None:
        fact = parse_numeric(
            "102",
            "fever.maximum_temperature",
            english,
            unit="fahrenheit",
            units=("fahrenheit", "celsius"),
        )
        assert fact.certainty is Certainty.PROBABLE

    def test_out_of_range_is_not_an_answer(self, english) -> None:
        """A temperature of 9 is a mistake, not a reading."""
        fact = parse_numeric(
            "9", "fever.maximum_temperature", english, minimum=30, maximum=110
        )
        assert fact.usable is False

    def test_devanagari_numerals(self, hindi) -> None:
        fact = parse_numeric("५ दिन", "sleep.hours", hindi)
        assert fact.value == 5

    def test_number_words(self, english) -> None:
        assert parse_numeric("five", "sleep.hours", english).value == 5


class TestSeveralFactsFromOneSentence:
    """§13's worked example, which is the claim the whole free-text path makes."""

    def test_a_pain_description_yields_three_facts(self, english) -> None:
        facts = {
            fact.slot: fact.value
            for fact in parse_free_text(
                "It's a burning pain on the right side of my stomach "
                "and gets worse after eating.",
                ("pain.character", "pain.site", "pain.aggravating"),
                _slots(),
                english,
            )
        }
        assert facts["pain.character"] == "burning"
        assert facts["pain.site"] == "upper_abdomen"
        assert "eating" in str(facts["pain.aggravating"])

    def test_a_slot_the_sentence_says_nothing_about_stays_empty(self, english) -> None:
        """No slot is filled because the sentence was long."""
        facts = parse_free_text(
            "It's a burning pain.",
            ("pain.character", "pain.radiation"),
            _slots(),
            english,
        )
        assert {f.slot for f in facts} == {"pain.character"}

    def test_a_timeline_sentence_yields_duration_and_progression(self, english) -> None:
        facts = {
            fact.slot: fact.value
            for fact in parse_free_text(
                "started about three days ago, getting worse",
                ("fever.duration", "fever.progression"),
                _slots(),
                english,
            )
        }
        assert facts["fever.duration"]["value"] == 3
        assert facts["fever.progression"] == "worsening"


class TestOptions:
    def test_a_multi_select_keeps_every_match_in_order(self, english) -> None:
        fact = parse_multi_select(
            "fever and headache",
            "routing.complaints",
            ("fever", "headache", "cough"),
            english,
        )
        assert fact.value == ["fever", "headache"]

    def test_two_matches_are_not_one_single_select_answer(self, english) -> None:
        """"Sometimes burning, sometimes cramping" is not an answer to a
        single-select, and picking the first would throw away half the
        sentence."""
        fact = parse_single_select(
            "sometimes burning, sometimes cramping",
            "pain.character",
            ("burning", "cramping"),
            english,
        )
        assert fact.usable is False


def _slots():  # type: ignore[no-untyped-def]
    from pathlib import Path

    from app.questioning_agent.knowledge.information_schema import SlotRegistry

    return SlotRegistry.load(
        Path(__file__).resolve().parents[3] / "clinical" / "questioning"
    )
