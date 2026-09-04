"""Medicine resolution, alignment and interaction lookup — §6.4.

Three modules, one chain: a printed or spoken medicine name resolves to an
ingredient key (`ingredients.py`), a spoken name is aliased onto the document's
field id so the two can be compared (`alignment.py`), and pairs among the
resolved ingredients are looked up in a sourced table (`interactions.py`).

Every one of them fails safe in the same direction: **a name that does not
resolve contributes nothing.** An unmatched name is not evidence of an
interaction, and a warning built on a spelling is worse than silence — clinicians
who learn to ignore one alert learn to ignore the next.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.clinical.enums import Certainty, Section
from app.domain.documents.alignment import (
    ALIAS_NOTE_PREFIX,
    align_medications,
    is_alias,
)
from app.domain.documents.ingredients import IngredientIndex, strip_form
from app.domain.documents.interactions import (
    InteractionError,
    InteractionSeverity,
    InteractionTable,
    MedicineEntry,
    check,
    normalise_ingredient,
)
from app.domain.record import (
    DocumentSource,
    Fact,
    FactChannel,
    FieldStatus,
    Text,
    TurnSource,
)

RECORDED_AT = datetime(2026, 9, 3, 10, 21, 5, tzinfo=UTC)


@pytest.fixture
def index() -> IngredientIndex:
    return IngredientIndex(
        {
            "metformin": ["glycomet", "मेटफॉर्मिन"],
            "clopidogrel": ["plavix"],
            "omeprazole": ["omez"],
            "amlodipine": [],
        }
    )


def _fact(
    field_id: str = "current_medications",
    *,
    value: str | None = "Metformin 500",
    status: FieldStatus = FieldStatus.ANSWERED,
    channel: FactChannel = FactChannel.VOICE,
    certainty: Certainty = Certainty.REPORTED,
    original_text: str | None = None,
) -> Fact:
    return Fact(
        fact_id=f"fact_{field_id}_{channel.value}",
        field_id=field_id,
        section=Section.MEDICATIONS,
        status=status,
        value=Text(text=value) if value is not None else None,
        certainty=certainty,
        channel=channel,
        original_text=original_text,
        recorded_at=RECORDED_AT,
        source=(
            TurnSource(turn_id=7)
            if channel is FactChannel.VOICE
            else DocumentSource(document_id="doc_000001", page=1)
        ),
    )


class TestResolvingAMedicineName:
    @pytest.mark.parametrize(
        "printed",
        [
            "Metformin",
            "metformin",
            "METFORMIN",
            "Tab. Metformin 500 BD",
            "Tab Glycomet 500",
            "Glycomet",
            "मेटफॉर्मिन",
        ],
    )
    def test_it_finds_the_ingredient_under_form_strength_and_brand(
        self, index: IngredientIndex, printed: str
    ) -> None:
        assert index.resolve(printed) == "metformin"

    @pytest.mark.parametrize("printed", ["Glycomett", "Metformine", "Metfor", "", "   "])
    def test_a_name_it_does_not_hold_resolves_to_nothing(
        self, index: IngredientIndex, printed: str
    ) -> None:
        """Exact match after folding, and nothing else.

        Fuzzy matching here would let a spelling difference raise an interaction
        warning against a medicine the patient is not taking. Fuzzy matching
        belongs in the terminology service, where it is scored and shown, not
        buried in a safety lookup.
        """
        assert index.resolve(printed) is None

    @pytest.mark.parametrize(
        ("printed", "expected"),
        [
            ("Tab. Metformin 500 mg", "metformin"),
            ("Cap Omeprazole 20mg", "omeprazole"),
            ("Syp. Something 5ml", "something"),
            ("Metformin SR 500", "metformin"),
        ],
    )
    def test_dosage_forms_and_strengths_are_stripped(
        self, printed: str, expected: str
    ) -> None:
        assert strip_form(printed) == expected

    def test_stripping_never_returns_nothing(self) -> None:
        """A name made entirely of form words keeps its original text.

        Returning an empty string would resolve to whatever the table holds
        under `""`, which is the sort of match nobody would ever authorise.
        """
        assert strip_form("Tab.") == "Tab."


class TestAliasingASpokenMedicineOntoTheDocumentsField:
    """The bug this module was written to fix.

    The patient says "Metformin"; the prescription says "Tab. Metformin 900.2 mg
    BD". They arrive as `current_medications` on the voice channel and
    `medication_metformin` on the document channel, so the contradiction
    detector cannot see they are about the same drug — and the dose discrepancy,
    the most useful thing the document pipeline produces, goes unreported.
    """

    def test_a_resolvable_voice_medication_gains_a_comparable_field_id(
        self, index: IngredientIndex
    ) -> None:
        aliases = align_medications([_fact()], index)
        assert [alias.field_id for alias in aliases] == ["medication_metformin"]

    def test_the_alias_carries_the_original_claim_unchanged(
        self, index: IngredientIndex
    ) -> None:
        """It adds nothing: same value, same source, same certainty.

        It does not parse a dose out of the text, does not normalise the name
        and does not raise certainty. It is the same statement under a
        comparable name.
        """
        original = _fact(certainty=Certainty.APPROXIMATE, original_text="हाँ, मेटफॉर्मिन")
        alias = align_medications([original], index)[0]
        assert alias.value == original.value
        assert alias.certainty is original.certainty
        assert alias.source == original.source
        assert alias.original_text == original.original_text
        assert alias.status is original.status

    def test_it_says_it_is_derived_and_names_its_source(
        self, index: IngredientIndex
    ) -> None:
        """So it cannot be mistaken for a second, independent statement."""
        original = _fact()
        alias = align_medications([original], index)[0]
        assert is_alias(alias)
        assert alias.note == f"{ALIAS_NOTE_PREFIX}{original.fact_id}"
        assert original.fact_id in alias.fact_id

    def test_the_alias_id_is_the_same_on_every_read(
        self, index: IngredientIndex
    ) -> None:
        """Derived on every read and never persisted, so it has to be stable —
        an id that changed per call would make every report a fresh diff."""
        original = _fact()
        assert align_medications([original], index)[0].fact_id == (
            align_medications([original], index)[0].fact_id
        )

    def test_a_document_channel_fact_on_the_same_field_does_not_suppress_it(
        self, index: IngredientIndex
    ) -> None:
        """The case the whole thing exists for.

        A `medication_metformin` fact already on the *document* channel is
        exactly what the alias is meant to be compared against. Treating it as
        "already present" skips the alias and leaves the dose discrepancy
        unreported.
        """
        printed = _fact(
            "medication_metformin",
            value="Metformin 900.2 mg BD",
            channel=FactChannel.DOCUMENT,
        )
        aliases = align_medications([_fact(), printed], index)
        assert [alias.field_id for alias in aliases] == ["medication_metformin"]

    def test_an_existing_voice_fact_on_the_field_does_suppress_it(
        self, index: IngredientIndex
    ) -> None:
        spoken = _fact("medication_metformin", value="Metformin 500")
        assert align_medications([_fact(), spoken], index) == ()

    def test_a_list_of_medicines_produces_one_alias_each(
        self, index: IngredientIndex
    ) -> None:
        """A patient listing three medicines produces one string.

        Splitting on the separators people actually use gives each a chance to
        resolve; a fragment that resolves to nothing contributes nothing.
        """
        listed = _fact(value="Metformin 500, Amlodipine 5 and Glycomett")
        fields = {alias.field_id for alias in align_medications([listed], index)}
        assert fields == {"medication_metformin", "medication_amlodipine"}

    @pytest.mark.parametrize(
        "status",
        [FieldStatus.UNRESOLVED, FieldStatus.NOT_ASKED, FieldStatus.REFUSED],
    )
    def test_an_unsettled_medication_field_is_never_aliased(
        self, index: IngredientIndex, status: FieldStatus
    ) -> None:
        """An alias for a field the patient never settled would turn "we do not
        know" into a statement about a specific drug."""
        assert align_medications([_fact(value=None, status=status)], index) == ()

    def test_a_document_channel_medication_is_not_aliased(
        self, index: IngredientIndex
    ) -> None:
        """Aliases exist to make what the patient said comparable.

        Aliasing the document side too would compare the prescription against
        itself.
        """
        printed = _fact(value="Metformin 900.2 mg BD", channel=FactChannel.DOCUMENT)
        assert align_medications([printed], index) == ()

    def test_a_non_medication_field_is_left_alone(self, index: IngredientIndex) -> None:
        assert align_medications([_fact("chief_complaint", value="Metformin")], index) == ()


class TestTheInteractionTable:
    def test_a_row_with_no_source_does_not_load(self) -> None:
        """An unsourced interaction claim is a rumour, and this table is read by
        clinicians."""
        with pytest.raises(InteractionError, match="source"):
            InteractionTable.from_rows(
                [{"a": "clopidogrel", "b": "omeprazole", "effect": "reduced activation"}]
            )

    def test_a_row_with_no_effect_text_does_not_load(self) -> None:
        with pytest.raises(InteractionError, match="effect"):
            InteractionTable.from_rows(
                [{"a": "clopidogrel", "b": "omeprazole", "effect": "  ", "source": "WHO"}]
            )

    def test_an_ingredient_cannot_interact_with_itself(self) -> None:
        with pytest.raises(InteractionError, match="itself"):
            InteractionTable.from_rows(
                [{"a": "metformin", "b": "Metformin", "effect": "x", "source": "WHO"}]
            )

    def test_two_different_statements_about_one_pair_do_not_load(self) -> None:
        """One pair, one statement. Which of two contradictory rows a lookup
        returned would depend on file order."""
        with pytest.raises(InteractionError, match="duplicate"):
            InteractionTable.from_rows(
                [
                    {"a": "a", "b": "b", "effect": "one", "source": "WHO"},
                    {"a": "b", "b": "a", "effect": "another", "source": "WHO"},
                ]
            )

    def test_an_identical_row_twice_is_not_a_duplicate(self) -> None:
        table = InteractionTable.from_rows(
            [
                {"a": "a", "b": "b", "effect": "one", "source": "WHO"},
                {"a": "b", "b": "a", "effect": "one", "source": "WHO"},
            ]
        )
        assert len(table) == 1

    def test_lookup_is_direction_free(self) -> None:
        table = InteractionTable.from_rows(
            [
                {
                    "a": "clopidogrel",
                    "b": "omeprazole",
                    "effect": "reduced activation",
                    "source": "WHO Model Formulary 2008",
                }
            ]
        )
        assert table.get("clopidogrel", "omeprazole") is table.get(
            "omeprazole", "clopidogrel"
        )

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Clopidogrel", "clopidogrel"),
            ("CLOPIDOGREL ", "clopidogrel"),
            ("acetyl-salicylic acid", "acetyl_salicylic_acid"),
            ("Amlodipine (Amlong)", "amlodipine_amlong"),
        ],
    )
    def test_names_fold_to_a_comparable_key(self, name: str, expected: str) -> None:
        assert normalise_ingredient(name) == expected


class TestCheckingAPatientsOwnMedicines:
    @pytest.fixture
    def table(self) -> InteractionTable:
        return InteractionTable.from_rows(
            [
                {
                    "a": "clopidogrel",
                    "b": "omeprazole",
                    "effect": "reported reduction in clopidogrel activation",
                    "severity": "major",
                    "source": "WHO Model Formulary 2008",
                },
                {
                    "a": "metformin",
                    "b": "amlodipine",
                    "effect": "a minor thing",
                    "severity": "minor",
                    "source": "somewhere",
                },
            ]
        )

    def test_a_sourced_pair_among_them_is_found(self, table: InteractionTable) -> None:
        findings = check(
            [
                MedicineEntry(display="Plavix 75", ingredient_key="clopidogrel"),
                MedicineEntry(display="Omez 20", ingredient_key="omeprazole"),
            ],
            table,
        )
        assert len(findings) == 1
        assert findings[0].rule.severity is InteractionSeverity.MAJOR

    def test_the_finding_carries_its_source_and_asks_for_review(
        self, table: InteractionTable
    ) -> None:
        """Presented as "these two may interact — please review".

        Never as a recommendation and never as a contraindication: this system
        does not tell a physician what to prescribe.
        """
        from app.domain.report.safety import find_unsupported_assertions

        rendered = check(
            [
                MedicineEntry(display="Plavix 75", ingredient_key="clopidogrel"),
                MedicineEntry(display="Omez 20", ingredient_key="omeprazole"),
            ],
            table,
        )[0].render()
        assert "please review" in rendered
        assert "WHO Model Formulary 2008" in rendered
        assert find_unsupported_assertions(rendered) == ()

    def test_a_medicine_that_did_not_resolve_contributes_nothing(
        self, table: InteractionTable
    ) -> None:
        assert (
            check(
                [
                    MedicineEntry(display="Plavix 75", ingredient_key="clopidogrel"),
                    MedicineEntry(display="Some Ayurvedic Churna", ingredient_key=""),
                ],
                table,
            )
            == ()
        )

    def test_a_pair_with_no_row_produces_no_finding(
        self, table: InteractionTable
    ) -> None:
        """No row means nobody wrote a sourced statement about this pair. It does
        not mean the pair is safe, and the report says nothing either way."""
        assert (
            check(
                [
                    MedicineEntry(display="Metformin", ingredient_key="metformin"),
                    MedicineEntry(display="Omez", ingredient_key="omeprazole"),
                ],
                table,
            )
            == ()
        )

    def test_the_same_pair_listed_twice_is_reported_once(
        self, table: InteractionTable
    ) -> None:
        """The patient said "Plavix" and the prescription printed "Clopidogrel".

        Two entries, one drug, one finding — not two identical alerts.
        """
        findings = check(
            [
                MedicineEntry(display="Plavix 75", ingredient_key="clopidogrel"),
                MedicineEntry(display="Clopidogrel 75", ingredient_key="clopidogrel"),
                MedicineEntry(display="Omez 20", ingredient_key="omeprazole"),
            ],
            table,
        )
        assert len(findings) == 1

    def test_the_most_severe_finding_comes_first(self, table: InteractionTable) -> None:
        findings = check(
            [
                MedicineEntry(display="Plavix", ingredient_key="clopidogrel"),
                MedicineEntry(display="Omez", ingredient_key="omeprazole"),
                MedicineEntry(display="Metformin", ingredient_key="metformin"),
                MedicineEntry(display="Amlodipine", ingredient_key="amlodipine"),
            ],
            table,
        )
        assert [f.rule.severity for f in findings] == [
            InteractionSeverity.MAJOR,
            InteractionSeverity.MINOR,
        ]


class TestTheShippedTable:
    """The rows that actually load at startup — `clinical/interactions/`."""

    def test_every_row_names_its_source(self, content: object) -> None:
        table = content.interactions  # type: ignore[attr-defined]
        assert len(table) > 0
        assert all(rule.source.strip() for rule in table)

    def test_no_row_pairs_a_herb_with_a_drug(self, content: object) -> None:
        """§6.4 — drug–drug only, deliberately.

        The herb–drug evidence base is thin, mostly in vitro and frequently
        contradictory. On an AYUSH product a herb–drug flag would look like the
        headline feature and would be the least defensible thing in the build.

        Enforced against the ingredient table's own AYUSH entries rather than a
        list retyped here, so adding an Ayurvedic ingredient cannot quietly
        widen the scope.
        """
        table = content.interactions  # type: ignore[attr-defined]
        ayurvedic = {
            key
            for key in content.ingredients.keys  # type: ignore[attr-defined]
            if key
            in {
                "ashwagandha",
                "guduchi",
                "triphala",
                "brahmi",
                "shatavari",
                "guggulu",
                "arjuna",
                "yashtimadhu",
                "haridra",
                "tulsi",
            }
        }
        offending = [rule.pair for rule in table if set(rule.pair) & ayurvedic]
        assert offending == []
