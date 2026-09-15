import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr.metrics import (  # noqa: E402
    character_error_rate,
    keyword_recall,
    normalize,
    word_error_rate,
)


def test_normalize_composes_devanagari_and_drops_punctuation():
    # The same word decomposed vs composed must compare equal, or every matra reads as an error.
    decomposed = "दर्द"
    assert normalize(decomposed) == normalize("दर्द")
    assert normalize("मधुमेह।") == "मधुमेह"
    assert normalize("  two   spaces ") == "two spaces"


def test_error_rates_are_zero_for_an_exact_read():
    reference = "Metformin 500 mg 1-0-1"
    assert character_error_rate(reference, reference) == 0.0
    assert word_error_rate(reference, reference) == 0.0


def test_error_rates_scale_with_damage():
    reference = "Metformin 500 mg"
    close = character_error_rate(reference, "Metformin 500 rng")
    wrong = character_error_rate(reference, "कुछ और लिखा है")
    assert 0 < close < 0.2
    assert wrong > close


def test_empty_hypothesis_is_a_total_miss_not_a_pass():
    assert character_error_rate("Metformin", "") == 1.0
    assert word_error_rate("Metformin 500 mg", "") == 1.0


def test_keyword_recall_tracks_the_tokens_that_matter():
    hypothesis = "Rx Metformin 500 mg 1-0-1 खाने के बाद"
    assert keyword_recall(["Metformin", "500 mg", "1-0-1"], hypothesis) == 1.0
    # A model can read most of a page and still drop the drug name.
    assert keyword_recall(["Metformin", "Pantoprazole"], hypothesis) == 0.5
    assert keyword_recall(["Pantoprazole"], hypothesis) == 0.0


def test_table_markup_is_not_counted_as_a_reading_error():
    """A document model returns structure; structure is not a mistake.

    PaddleOCR-VL scored CER 0.63 on a lab report it had read perfectly, purely because it wrapped
    the values in an HTML table.
    """

    reference = "Haemoglobin 11.0 g/dL 12.0 - 15.0"
    as_table = (
        "<table><tr><td>Haemoglobin</td><td>11.0</td>"
        "<td>g/dL</td><td>12.0 - 15.0</td></tr></table>"
    )
    assert character_error_rate(reference, as_table) < 0.05
    assert normalize("## Heading **bold**") == "Heading bold"


def test_fuzzy_keyword_recall_rescues_near_misses_exact_matching_drops():
    """PP-OCRv5 read पेरासीटामोल as पेरासीरामेल - one character out, and a drug list would fix it."""

    from ocr.metrics import keyword_recall_fuzzy

    hypothesis = "टेबलेट पेरासीरामेल ६५० एमजी रोज एक गोली"
    assert keyword_recall(["पेरासीटामोल"], hypothesis) == 0.0
    assert keyword_recall_fuzzy(["पेरासीटामोल"], hypothesis) == 1.0
    # Fuzzy must stay strict enough to reject a genuinely different drug.
    assert keyword_recall_fuzzy(["पेंटोप्राजोल"], hypothesis) == 0.0


def test_fuzzy_recall_is_never_below_exact_recall():
    """Fuzzy is a superset of exact. It briefly was not: window alignment missed a multi-word
    keyword that was present verbatim, so PP-OCRv5 scored 0.806 fuzzy against 0.814 exact."""

    from ocr.metrics import keyword_recall_fuzzy

    hypothesis = "ER RECORD District Hospital Damoh Casualty"
    words = ["District Hospital Damoh", "ER RECORD", "Casualty", "Paracetamol"]
    assert keyword_recall_fuzzy(words, hypothesis) >= keyword_recall(words, hypothesis)
    assert keyword_recall_fuzzy(words, hypothesis) == 0.75
