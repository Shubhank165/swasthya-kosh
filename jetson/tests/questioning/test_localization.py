"""Nine complete banks — §22, §25, §31.

The rule the project already runs on: **a missing string is a build failure, not
a fallback.** Flutter's own behaviour, and everybody else's, is to fall back to
the template locale — which for a clinical questionnaire means a Tamil speaker
being shown an English question in the middle of a Tamil screen, answering it,
and a record saying they answered something they may not have understood.

So these tests check for holes, and for the subtler failure of a hole filled
with English.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from questioning_agent.core.agent import QuestioningAgent
from questioning_agent.knowledge.questions import QuestionBank
from questioning_agent.localization.languages import LANGUAGES, Vocabularies
from questioning_agent.localization.localization_loader import Localization
from tests.questioning.conftest import CONTENT, started

#: Words that would only appear in a non-English bank by being left there.
_PLACEHOLDERS = ("TODO", "TRANSLATE", "translation required", "FIXME", "XXX")


@pytest.fixture(scope="module")
def localization() -> Localization:
    return Localization.load(CONTENT)


@pytest.fixture(scope="module")
def vocabularies() -> Vocabularies:
    return Vocabularies.load(CONTENT)


class TestEveryLanguageIsComplete:
    def test_all_nine_banks_exist(self) -> None:
        for language in LANGUAGES:
            path = CONTENT / "localization" / f"questions_{language}.json"
            assert path.exists(), language

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_every_question_has_text(
        self, language: str, localization: Localization, agent: QuestioningAgent
    ) -> None:
        missing = [
            question.id
            for question in agent.bank.all
            if not localization.has_question(question.id, language)
        ]
        assert not missing, f"{language} is missing {missing}"

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_every_option_has_text(
        self, language: str, localization: Localization, agent: QuestioningAgent
    ) -> None:
        needed: set[str] = {domain.id for domain in agent.slots.domains}
        for question in agent.bank.all:
            needed |= set(question.options)
        for slot in agent.slots.all:
            needed |= set(slot.allowed_values)

        missing = sorted(o for o in needed if not localization.has_option(o, language))
        assert not missing, f"{language} is missing {missing}"

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_no_placeholders(self, language: str) -> None:
        body = json.loads(
            (CONTENT / "localization" / f"questions_{language}.json").read_text("utf-8")
        )
        for kind in ("questions", "options"):
            for key, text in body[kind].items():
                for placeholder in _PLACEHOLDERS:
                    assert placeholder.lower() not in text.lower(), f"{language} {key}"

    @pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "en"])
    def test_no_english_left_in_another_language(self, language: str) -> None:
        """The failure a completeness check alone does not catch.

        A file with every key present and the English string in half of them
        passes "nothing is missing" and fails the patient.

        A handful of entries are legitimately identical — `TB` is `टीबी` in
        transliteration but a few short forms genuinely carry across — so this
        allows a small number rather than zero, and fails on wholesale copying.
        """
        english = json.loads(
            (CONTENT / "localization" / "questions_en.json").read_text("utf-8")
        )
        other = json.loads(
            (CONTENT / "localization" / f"questions_{language}.json").read_text("utf-8")
        )
        identical = [
            key
            for kind in ("questions", "options")
            for key, text in other[kind].items()
            if english[kind].get(key) == text
        ]
        assert len(identical) <= 3, f"{language} reuses English for {identical}"

    def test_the_question_bank_is_language_independent(self) -> None:
        """§26. Ids, dependencies, scoring and answer types are the same in
        every language; only the text changes."""
        bank = QuestionBank.load(CONTENT, __import__(
            "questioning_agent.knowledge.information_schema",
            fromlist=["SlotRegistry"],
        ).SlotRegistry.load(CONTENT))
        assert bank.all, "no questions"
        # There is exactly one bank, loaded without a language at all — which is
        # the property being asserted.


class TestEveryLanguageCanParse:
    """§24. Each language brings its own normalisation layer."""

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_it_has_a_yes_and_a_no(
        self, language: str, vocabularies: Vocabularies
    ) -> None:
        vocabulary = vocabularies[language]
        assert vocabulary.affirm, language
        assert vocabulary.deny, language
        assert vocabulary.negation.cues, language

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_it_can_read_its_own_yes(
        self, language: str, vocabularies: Vocabularies
    ) -> None:
        """The check that would have caught the Devanagari tokenising bug.

        `\\w` does not match an Indic vowel sign, so `बुखार` split into three
        fragments and no Hindi answer matched anything. Seven of nine languages
        were silently unable to answer a single question, and the English tests
        all passed.
        """
        from questioning_agent.interpretation.boolean_parser import parse_boolean

        vocabulary = vocabularies[language]
        for word in sorted(vocabulary.affirm)[:5]:
            assert parse_boolean(word, "fever.present", vocabulary).value is True, (
                language,
                word,
            )
        for word in sorted(vocabulary.deny)[:5]:
            assert parse_boolean(word, "fever.present", vocabulary).value is False, (
                language,
                word,
            )

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_it_can_read_a_duration_in_its_own_script(
        self, language: str, vocabularies: Vocabularies
    ) -> None:
        from questioning_agent.interpretation.duration_parser import find_duration

        vocabulary = vocabularies[language]
        day_words = sorted(vocabulary.duration_units["day"], key=len, reverse=True)
        duration = find_duration(f"3 {day_words[0]}", vocabulary)
        assert duration is not None, (language, day_words[0])
        assert duration.unit == "day"


class TestInflectedForms:
    """The failure mode that stays after the tokeniser is fixed.

    Tamil, Telugu and Kannada attach "for"/"since" to the noun: `நாட்கள்` + `ஆக`
    becomes `நாட்களாக`, with the final pulli replaced — so the literal word from
    the vocabulary is not a substring of what the patient wrote. The vocabulary
    carries the stem for exactly this reason.

    This is what "the other languages are thinner" actually means: not broken
    machinery, missing surface forms, found one at a time by writing the
    sentence a patient would write.
    """

    @pytest.mark.parametrize(
        ("language", "text", "value", "unit"),
        [
            ("hi", "दो हफ्ते से", 2, "week"),
            ("bn", "তিন সপ্তাহে", 3, "week"),
            ("ta", "மூன்று நாட்களாக", 3, "day"),
            ("ta", "ஒரு வாரமாக", 1, "week"),
            ("ta", "இரண்டு மாதங்களாக", 2, "month"),
            ("te", "మూడు రోజులుగా", 3, "day"),
            ("te", "రెండు వారాలుగా", 2, "week"),
            ("mr", "दोन आठवड्यांपासून", 2, "week"),
            ("gu", "બે અઠવાડિયાથી", 2, "week"),
            ("kn", "ಮೂರು ದಿನಗಳಿಂದ", 3, "day"),
            ("kn", "ಎರಡು ವಾರಗಳಿಂದ", 2, "week"),
            ("pa", "ਦੋ ਹਫ਼ਤਿਆਂ ਤੋਂ", 2, "week"),
        ],
    )
    def test_a_declined_duration_still_parses(
        self,
        language: str,
        text: str,
        value: float,
        unit: str,
        vocabularies: Vocabularies,
    ) -> None:
        from questioning_agent.interpretation.duration_parser import find_duration

        duration = find_duration(text, vocabularies[language])
        assert duration is not None, (language, text)
        assert (duration.value, duration.unit) == (value, unit)

    @pytest.mark.parametrize(
        ("language", "text", "expected"),
        [
            ("hi", "हाँ, तीन दिन से बुखार है", True),
            ("hi", "नहीं, बुखार नहीं है", False),
            ("bn", "হ্যাঁ, তিন দিন ধরে জ্বর", True),
            ("bn", "না, জ্বর নেই", False),
            ("ta", "ஆம், மூன்று நாட்களாக காய்ச்சல்", True),
            ("ta", "இல்லை, காய்ச்சல் இல்லை", False),
            ("te", "అవును, మూడు రోజులుగా జ్వరం", True),
            ("te", "లేదు, జ్వరం లేదు", False),
            ("mr", "होय, तीन दिवसांपासून ताप", True),
            ("mr", "नाही, ताप नाही", False),
            ("gu", "હા, ત્રણ દિવસથી તાવ", True),
            ("gu", "ના, તાવ નથી", False),
            ("kn", "ಹೌದು, ಮೂರು ದಿನಗಳಿಂದ ಜ್ವರ", True),
            ("kn", "ಇಲ್ಲ, ಜ್ವರ ಇಲ್ಲ", False),
            ("pa", "ਹਾਂ, ਤਿੰਨ ਦਿਨਾਂ ਤੋਂ ਬੁਖ਼ਾਰ", True),
            ("pa", "ਨਹੀਂ, ਬੁਖ਼ਾਰ ਨਹੀਂ ਹੈ", False),
        ],
    )
    def test_a_whole_sentence_reads_correctly(
        self,
        language: str,
        text: str,
        expected: bool,
        vocabularies: Vocabularies,
    ) -> None:
        """A sentence, not a word. Every one of these denials contains the
        symptom word, which is the trap §16 exists for."""
        from questioning_agent.interpretation.boolean_parser import parse_boolean

        assert parse_boolean(text, "fever.present", vocabularies[language]).value is (
            expected
        ), (language, text)


class TestSwitchingLanguage:
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_an_interview_runs_end_to_end(
        self, language: str, agent: QuestioningAgent
    ) -> None:
        """The same engine, the same ids, nine different sets of words."""
        state = started(agent, ["fever"], language=language)
        assert state.active_domains == ("fever",)

        turn = agent.next(state, language=language)
        assert turn is not None
        assert turn.text
        assert turn.text == agent.localization.question_text(turn.id, language)

    def test_the_same_answers_give_the_same_facts_in_any_language(
        self, agent: QuestioningAgent
    ) -> None:
        """§23, and the acceptance criterion behind it: the logic is
        language-independent, only the presentation changes."""
        english = started(agent, ["fever"], language="en", timeline="three days")
        hindi = started(agent, ["fever"], language="hi", timeline="तीन दिन")

        assert english.value("fever.duration") == hindi.value("fever.duration")
        assert english.active_domains == hindi.active_domains

    def test_question_ids_do_not_change_with_language(
        self, agent: QuestioningAgent
    ) -> None:
        english = agent.next(started(agent, ["fever"], language="en"), language="en")
        hindi = agent.next(started(agent, ["fever"], language="hi"), language="hi")
        assert english is not None and hindi is not None
        assert english.id == hindi.id
        assert english.text != hindi.text


def test_the_generator_and_the_content_agree() -> None:
    """The committed files are what the generator would produce.

    The files are the source at runtime; the generator is the source for
    editing. A drift between them means somebody edited a generated file, and
    the next regeneration would silently discard their work.
    """
    import subprocess
    import sys

    # The generator is not vendored with the engine, so this check cannot run here. It is kept
    # rather than deleted: it is the only thing that would catch hand-edited localization JSON
    # drifting from the source content, and it should be restored with the script.
    generator = Path(__file__).resolve().parents[2] / "scripts" / "build_questioning_content.py"
    if not generator.exists():
        pytest.skip("scripts/build_questioning_content.py is not vendored with the engine")

    before = {
        path: path.read_bytes()
        for path in sorted((CONTENT / "localization").glob("*.json"))
    }
    result = subprocess.run(
        [sys.executable, "scripts/build_questioning_content.py"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    after = {path: path.read_bytes() for path in before}
    drifted = [p.name for p in before if before[p] != after[p]]
    assert not drifted, f"regenerating changed {drifted}"
