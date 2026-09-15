"""The handwritten/printed router, checked against confidences measured on the Jetson."""

from __future__ import annotations

import pytest

from medikiosk.kiosk import handwriting

# Measured on the Jetson with PP-OCRv5 over the sample set: (name, line count, share of lines
# scoring below 0.70, mean confidence). Six printed documents, seven photographs of handwritten
# OPD slips. These are observations, not fixtures - if the threshold stops separating them the
# threshold is wrong.
PRINTED = [
    ("discharge_note_clean", 11, 0.00, 0.969),
    ("discharge_note_photo", 8, 0.00, 0.930),
    ("lab_report_clean", 22, 0.00, 0.983),
    ("lab_report_photo", 19, 0.00, 0.944),
    ("prescription_clean", 15, 0.00, 0.975),
    ("prescription_photo", 11, 0.00, 0.904),
]
HANDWRITTEN = [
    ("opd_slip_a", 39, 0.33, 0.794),
    ("opd_slip_b", 42, 0.17, 0.808),
    ("opd_slip_c", 40, 0.35, 0.790),
    ("opd_slip_d", 43, 0.16, 0.853),
    ("opd_slip_e", 36, 0.11, 0.894),
    ("opd_slip_f", 27, 0.44, 0.730),
    ("opd_slip_g", 75, 0.32, 0.764),
]


def scores_for(lines: int, low_share: float) -> list[float]:
    """Rebuild a plausible score list with the measured line count and low-confidence share."""

    low = round(lines * low_share)
    return [0.55] * low + [0.95] * (lines - low)


@pytest.mark.parametrize(("name", "lines", "low_share", "_mean"), PRINTED)
def test_printed_documents_stay_on_the_jetson(name, lines, low_share, _mean) -> None:
    """A printed page must never be sent to the cloud reader: it is readable here, and sending it
    puts a patient's document outside the building for nothing."""

    assert handwriting.looks_handwritten(scores_for(lines, low_share)) is False, name


@pytest.mark.parametrize(("name", "lines", "low_share", "_mean"), HANDWRITTEN)
def test_handwritten_documents_are_routed_out(name, lines, low_share, _mean) -> None:
    """Missing one of these is the failure the router exists to prevent - the recognizer cannot
    read handwriting, so the doctor would get a page of nonsense with nothing marking it as such."""

    assert handwriting.looks_handwritten(scores_for(lines, low_share)) is True, name


def test_the_mean_would_not_have_separated_them() -> None:
    """Guards the design choice: the tail is the discriminator, not the average.

    Printed bottoms out at 0.904 and handwritten tops out at 0.894. Any router built on mean
    confidence has a one-hundredth margin and would misroute on the first blurry photograph.
    """

    worst_printed = min(mean for *_, mean in PRINTED)
    best_handwritten = max(mean for *_, mean in HANDWRITTEN)
    assert worst_printed - best_handwritten < 0.02


def test_the_threshold_sits_inside_the_measured_gap() -> None:
    highest_printed = max(share for _, _, share, _ in PRINTED)
    lowest_handwritten = min(share for _, _, share, _ in HANDWRITTEN)
    assert highest_printed < handwriting.HANDWRITTEN_LOW_LINE_SHARE < lowest_handwritten


def test_too_little_text_is_undecided_rather_than_printed() -> None:
    """An undecided page has not been shown to be printed, and the caller must not read it as such.

    A near-blank capture - a hand over the lens, a blank sheet - would otherwise be called printed
    and quietly kept local.
    """

    verdict = handwriting.assess([0.95, 0.94, 0.96])
    assert verdict.handwritten is None
    assert verdict.decided is False
    assert "too little" in verdict.reason


def test_no_text_at_all_is_undecided() -> None:
    verdict = handwriting.assess([])
    assert verdict.handwritten is None
    assert verdict.lines == 0
    assert "no text" in verdict.reason


def test_the_verdict_carries_why() -> None:
    """The reason goes on the record: a document routed to the cloud has to be explainable."""

    verdict = handwriting.assess(scores_for(40, 0.35))
    assert verdict.handwritten is True
    assert verdict.lines == 40
    assert verdict.low_line_share == pytest.approx(0.35, abs=0.02)
    assert "below 0.7" in verdict.reason
