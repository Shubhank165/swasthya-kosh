"""Decide whether a photographed document is handwritten, from the OCR's own confidence.

Why there is no classifier model here
-------------------------------------
The obvious design is a second model that looks at the image and says handwritten or printed. This
does the same job with a number PP-OCRv5 already computes on the way past, which costs no training
data, no extra weights on a board with about 2 GB free, and no second thing to keep loaded.

The signal works because the recognizer is trained on printed Devanagari. Handwriting does not
merely come out wrong - the model reports that it is unsure, line by line.

What the threshold is calibrated on
-----------------------------------
Thirteen documents, measured on the Jetson itself: six printed (clean scans and camera
photographs) and seven photographs of real handwritten OPD slips.

The mean confidence is a bad separator - printed bottoms out at 0.904 and handwritten tops out at
0.894, a gap of one hundredth. The *tail* separates cleanly:

    fraction of lines scoring below 0.70
      printed      0%  0%  0%  0%  0%  0%
      handwritten  11% 16% 17% 32% 33% 35% 44%

Not one printed document produced a single low-confidence line; every handwritten one produced at
least one in nine. That is the whole discriminator, and it makes sense for these documents: a
government OPD slip is a printed form with handwriting inked into it, so the printed labels keep
scoring high and pull the mean up, while the handwritten fills leave a low tail that a wholly
printed page never has.

Thirteen samples is a small set. The gap between 0% and 11% is wide enough to sit a threshold in
with margin, but this is calibration, not proof, and `looks_handwritten` returns None rather than
guessing when there is too little text to judge.

Which way the errors hurt
-------------------------
Calling a printed document handwritten sends a readable page to the cloud reader: slower, and the
image leaves the building for no benefit. Calling a handwritten document printed keeps it on the
Jetson, where the recognizer cannot read it, and the doctor gets a page of nonsense. The second is
the failure this exists to prevent, so the threshold sits nearer the printed side of the gap.
"""

from __future__ import annotations

from dataclasses import dataclass

# A line the recognizer is unsure about. Every printed sample scored above this on every line.
LOW_CONFIDENCE_LINE = 0.70

# Share of low-confidence lines above which the page is treated as handwritten. Measured printed
# documents sit at 0%, handwritten at 11% or more; 5% sits in that gap with room on both sides.
HANDWRITTEN_LOW_LINE_SHARE = 0.05

# Below this many recognized lines the share is too noisy to mean anything - one bad line out of
# three is 33% and says nothing. A blank or near-blank capture is not a handwriting judgement.
MIN_LINES_TO_JUDGE = 6


@dataclass(frozen=True)
class Verdict:
    """What the confidence tail says about one captured document."""

    handwritten: bool | None
    lines: int
    low_line_share: float
    mean_confidence: float
    reason: str

    @property
    def decided(self) -> bool:
        return self.handwritten is not None


def assess(scores: list[float]) -> Verdict:
    """Judge one document from its per-line recognition confidences.

    `handwritten` is None when there is not enough text to judge, which the caller must treat as
    "do not route to the cloud" rather than as False - an undecided page has not been shown to be
    printed.
    """

    lines = len(scores)
    if lines == 0:
        return Verdict(None, 0, 0.0, 0.0, "no text was recognized")

    mean = sum(scores) / lines
    low_share = sum(1 for s in scores if s < LOW_CONFIDENCE_LINE) / lines

    if lines < MIN_LINES_TO_JUDGE:
        return Verdict(
            None, lines, low_share, mean,
            f"only {lines} lines recognized; too little to judge",
        )

    handwritten = low_share > HANDWRITTEN_LOW_LINE_SHARE
    return Verdict(
        handwritten, lines, low_share, mean,
        f"{low_share:.0%} of {lines} lines scored below {LOW_CONFIDENCE_LINE}",
    )


def looks_handwritten(scores: list[float]) -> bool | None:
    """Shorthand for `assess(scores).handwritten`."""

    return assess(scores).handwritten
