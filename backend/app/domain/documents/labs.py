"""Out-of-range flagging.

**Arithmetic, not a model.** A value is compared against the range printed on
that same report and nothing else.

Never against a hardcoded range. Reference intervals vary by laboratory, by
assay method, by age and by sex; the interval that makes a haemoglobin of 11.6
normal in one lab makes it low in another. A document that printed no range gets
`RANGE_UNAVAILABLE` and no flag — saying nothing is correct, and inventing a
comparison would be manufacturing a clinical finding out of a formatting gap.

There is also no unit conversion here. `mg/dL` and `mmol/L` are not compared;
mismatched units give `NOT_COMPARABLE`. Converting silently is how a glucose of
5.5 becomes a hypoglycaemia alert.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.domain.documents.extraction import LabResult, RangeStatus, ReferenceRange

#: `12.0 - 15.0`, `12.0–15.0`, `12.0 to 15.0`
_INTERVAL = re.compile(
    r"(?P<low>-?\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(?P<high>-?\d+(?:\.\d+)?)"
)
#: `< 200`, `<= 200`, `≤ 200`, `up to 200`
_UPPER_ONLY = re.compile(r"(?:<=?|≤|up\s+to)\s*(?P<high>-?\d+(?:\.\d+)?)")
#: `> 40`, `>= 40`, `≥ 40`
_LOWER_ONLY = re.compile(r"(?:>=?|≥)\s*(?P<low>-?\d+(?:\.\d+)?)")


def parse_reference_range(raw: str | None, *, unit: str | None = None) -> ReferenceRange | None:
    """The range printed on the document, or `None` when none was printed.

    `None` is the honest answer far more often than it looks, and every caller
    must treat it as "do not flag" rather than "assume normal".
    """
    if not raw:
        return None
    text = raw.strip()
    interval = _INTERVAL.search(text)
    if interval is not None:
        return ReferenceRange(
            low=float(interval.group("low")),
            high=float(interval.group("high")),
            unit=unit,
            raw_text=text,
        )
    upper = _UPPER_ONLY.search(text)
    if upper is not None:
        return ReferenceRange(high=float(upper.group("high")), unit=unit, raw_text=text)
    lower = _LOWER_ONLY.search(text)
    if lower is not None:
        return ReferenceRange(low=float(lower.group("low")), unit=unit, raw_text=text)
    return None


def _units_comparable(value_unit: str | None, range_unit: str | None) -> bool:
    """True when the two units may be compared directly.

    A missing unit on either side is treated as comparable: many reports print
    the unit once in a column header, and refusing to compare then would
    suppress every flag on an otherwise perfectly legible report. A *mismatch*
    is never papered over.
    """
    if not value_unit or not range_unit:
        return True
    return _fold_unit(value_unit) == _fold_unit(range_unit)


def _fold_unit(unit: str) -> str:
    """A comparable form of a printed unit.

    NFKD first, because a document can carry the micro sign (U+00B5) or the
    Greek mu (U+03BC) for the same `µg/L` and OCR emits whichever it saw.
    Folding only one of them makes `µg/L` and `ug/L` a unit *mismatch*, which
    suppresses a legitimate flag — the failure is silent and looks like caution.
    """
    folded = unicodedata.normalize("NFKD", unit.strip().lower())
    return folded.replace(" ", "").replace("\u03bc", "u")


def classify(result: LabResult, *, needs_verification: bool = False) -> RangeStatus:
    """Where `result` sits against its own printed range.

    A value the OCR pass was unsure of is `NOT_COMPARABLE`: comparing a digit we
    do not trust produces a flag we do not trust, and an out-of-range alert on a
    misread number is worse than no alert at all.
    """
    if result.value is None:
        return RangeStatus.NOT_COMPARABLE
    if needs_verification:
        return RangeStatus.NOT_COMPARABLE
    reference = result.reference_range
    if reference is None:
        return RangeStatus.RANGE_UNAVAILABLE
    if not _units_comparable(result.unit, reference.unit):
        return RangeStatus.NOT_COMPARABLE
    if reference.low is not None and result.value < reference.low:
        return RangeStatus.BELOW_RANGE
    if reference.high is not None and result.value > reference.high:
        return RangeStatus.ABOVE_RANGE
    return RangeStatus.IN_RANGE


@dataclass(frozen=True, slots=True)
class RangeNote:
    """How an out-of-range value is worded on the report.

    Descriptive only. It states where the number sits relative to the printed
    interval and stops there — it draws no conclusion, names no condition and
    recommends nothing, because all three would be a diagnosis.
    """

    analyte: str
    status: RangeStatus
    text: str


#: Wording per status. Flat statements of arithmetic.
_WORDING = {
    RangeStatus.BELOW_RANGE: "below the reference range printed on this report",
    RangeStatus.ABOVE_RANGE: "above the reference range printed on this report",
    RangeStatus.IN_RANGE: "within the reference range printed on this report",
    RangeStatus.RANGE_UNAVAILABLE: "no reference range printed on this report — not compared",
    RangeStatus.NOT_COMPARABLE: "not compared — the value or its unit could not be read reliably",
}


def note_for(result: LabResult, status: RangeStatus) -> RangeNote:
    """The report line for one classified result."""
    return RangeNote(analyte=result.analyte, status=status, text=_WORDING[status])


def is_flagged(status: RangeStatus) -> bool:
    """True only for a value that genuinely fell outside a printed range."""
    return status in {RangeStatus.BELOW_RANGE, RangeStatus.ABOVE_RANGE}
