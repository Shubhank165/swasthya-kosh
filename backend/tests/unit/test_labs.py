"""Out-of-range flagging — §6.5.

Arithmetic against the range printed on the same document, and nothing else.

The rule that carries the most weight is the negative one: **a document with no
printed range produces no flag.** Reference intervals vary by laboratory, by
assay method, by age and by sex, and the interval that makes a haemoglobin of
11.6 normal in one lab makes it low in another. Comparing against a range from
somewhere else manufactures a clinical finding out of a formatting gap.
"""

from __future__ import annotations

import pytest

from app.domain.documents.extraction import LabResult, RangeStatus, ReferenceRange
from app.domain.documents.labs import (
    classify,
    is_flagged,
    note_for,
    parse_reference_range,
)


def _result(
    value: float | None = 9.8,
    *,
    unit: str | None = "g/dL",
    reference: ReferenceRange | None = None,
) -> LabResult:
    return LabResult(
        analyte="Haemoglobin", value=value, unit=unit, reference_range=reference
    )


def _range(low: float | None = 12.0, high: float | None = 15.0, unit: str | None = "g/dL"):
    return ReferenceRange(low=low, high=high, unit=unit, raw_text="12.0 - 15.0 g/dL")


class TestParsingThePrintedRange:
    @pytest.mark.parametrize(
        ("raw", "low", "high"),
        [
            ("12.0 - 15.0", 12.0, 15.0),
            ("12.0–15.0 g/dL", 12.0, 15.0),
            ("12.0 to 15.0", 12.0, 15.0),
            ("70-100", 70.0, 100.0),
            ("-2.0 - 2.0", -2.0, 2.0),
        ],
    )
    def test_an_interval_is_read_whichever_dash_the_lab_printed(
        self, raw: str, low: float, high: float
    ) -> None:
        parsed = parse_reference_range(raw)
        assert parsed is not None
        assert (parsed.low, parsed.high) == (low, high)

    @pytest.mark.parametrize("raw", ["< 200", "<= 200", "≤ 200", "up to 200"])
    def test_an_upper_bound_alone_is_a_range(self, raw: str) -> None:
        parsed = parse_reference_range(raw)
        assert parsed is not None
        assert parsed.low is None
        assert parsed.high == 200.0

    @pytest.mark.parametrize("raw", ["> 40", ">= 40", "≥ 40"])
    def test_a_lower_bound_alone_is_a_range(self, raw: str) -> None:
        parsed = parse_reference_range(raw)
        assert parsed is not None
        assert parsed.high is None
        assert parsed.low == 40.0

    @pytest.mark.parametrize("raw", [None, "", "   ", "Normal", "see report", "WNL"])
    def test_anything_it_cannot_read_is_no_range_at_all(self, raw: str | None) -> None:
        """`None`, never a guess.

        "Normal" printed in a range column means the lab did not print an
        interval. Every caller must read `None` as "do not flag" rather than as
        "assume normal", which is what the classification below enforces.
        """
        assert parse_reference_range(raw) is None

    def test_the_raw_text_is_kept_so_the_report_can_print_it(self) -> None:
        parsed = parse_reference_range("12.0 - 15.0 g/dL")
        assert parsed is not None
        assert parsed.raw_text == "12.0 - 15.0 g/dL"
        assert parsed.render() == "12.0 - 15.0 g/dL"


class TestClassification:
    def test_below_a_printed_range_is_below(self) -> None:
        assert classify(_result(9.8, reference=_range())) is RangeStatus.BELOW_RANGE

    def test_above_a_printed_range_is_above(self) -> None:
        assert classify(_result(16.2, reference=_range())) is RangeStatus.ABOVE_RANGE

    def test_inside_a_printed_range_is_in_range(self) -> None:
        assert classify(_result(13.0, reference=_range())) is RangeStatus.IN_RANGE

    @pytest.mark.parametrize("value", [12.0, 15.0])
    def test_the_bounds_themselves_are_inside(self, value: float) -> None:
        """A reference interval is inclusive. 12.0 against 12.0–15.0 is normal,
        and flagging it would put a flag on half the healthy population."""
        assert classify(_result(value, reference=_range())) is RangeStatus.IN_RANGE

    def test_an_open_ended_range_only_flags_the_end_it_has(self) -> None:
        upper_only = ReferenceRange(high=200.0, unit="mg/dL")
        assert classify(_result(240.0, unit="mg/dL", reference=upper_only)) is (
            RangeStatus.ABOVE_RANGE
        )
        assert classify(_result(10.0, unit="mg/dL", reference=upper_only)) is (
            RangeStatus.IN_RANGE
        )


class TestTheCasesThatMustNotProduceAFlag:
    """Every one of these is a way to invent a finding, and each is refused."""

    def test_no_printed_range_is_range_unavailable_and_is_never_flagged(self) -> None:
        status = classify(_result(9.8, reference=None))
        assert status is RangeStatus.RANGE_UNAVAILABLE
        assert is_flagged(status) is False

    def test_a_value_the_ocr_pass_doubted_is_not_compared(self) -> None:
        """Comparing a digit we do not trust produces a flag we do not trust.

        The benchmark read `९००.२` for `१००.२`. An out-of-range alert on a
        misread number is worse than no alert: it is a false finding with a
        number beside it.
        """
        status = classify(_result(9.8, reference=_range()), needs_verification=True)
        assert status is RangeStatus.NOT_COMPARABLE
        assert is_flagged(status) is False

    def test_mismatched_units_are_not_converted(self) -> None:
        """`mg/dL` and `mmol/L` are not the same number.

        Converting silently is how a glucose of 5.5 becomes a hypoglycaemia
        alert.
        """
        mmol = ReferenceRange(low=3.9, high=5.6, unit="mmol/L")
        status = classify(_result(148.0, unit="mg/dL", reference=mmol))
        assert status is RangeStatus.NOT_COMPARABLE
        assert is_flagged(status) is False

    def test_a_value_that_was_not_read_at_all_is_not_compared(self) -> None:
        assert classify(_result(None, reference=_range())) is RangeStatus.NOT_COMPARABLE

    @pytest.mark.parametrize(
        ("value_unit", "range_unit"),
        [(None, "g/dL"), ("g/dL", None), (None, None), ("G/DL", "g/dl"), ("µg/L", "ug/L")],
    )
    def test_a_missing_or_differently_cased_unit_still_compares(
        self, value_unit: str | None, range_unit: str | None
    ) -> None:
        """Many reports print the unit once, in a column header.

        Refusing to compare then would suppress every flag on an otherwise
        perfectly legible report. A genuine *mismatch* is still never papered
        over — that is the test above.
        """
        reference = ReferenceRange(low=12.0, high=15.0, unit=range_unit)
        assert classify(_result(9.8, unit=value_unit, reference=reference)) is (
            RangeStatus.BELOW_RANGE
        )


class TestTheWording:
    @pytest.mark.parametrize("status", list(RangeStatus))
    def test_every_status_has_wording(self, status: RangeStatus) -> None:
        """A status added without wording would render a blank line on a report,
        which reads as "nothing to say" rather than as a missing string."""
        note = note_for(_result(), status)
        assert note.text.strip()

    @pytest.mark.parametrize("status", list(RangeStatus))
    def test_it_names_no_condition_and_recommends_nothing(
        self, status: RangeStatus
    ) -> None:
        """Descriptive only: where the number sits, and stop.

        Anything past that is a diagnosis, and this system does not make one.
        """
        from app.domain.report.safety import find_unsupported_assertions

        note = note_for(_result(), status)
        assert find_unsupported_assertions(note.text) == ()

    def test_only_a_genuine_excursion_counts_as_flagged(self) -> None:
        assert [status for status in RangeStatus if is_flagged(status)] == [
            RangeStatus.BELOW_RANGE,
            RangeStatus.ABOVE_RANGE,
        ]
