"""Report determinism — §13.12.

**The same canonical record renders byte-identical output every time.**

Golden files, checked in, diffed on every run. Two things this buys:

- A rendering change is a reviewable diff in a file a clinician can read, rather
  than a behaviour change nobody notices until a physician does.
- Nondeterminism — a set iteration, a dict ordering, a clock read that crept in —
  fails immediately instead of producing a report that is subtly different each
  time it is opened.

The report is built by template with no model anywhere in the path, so
determinism is achievable at all. That is most of the argument for the template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.domain.clinical.enums import Section
from app.domain.documents.extraction import DocumentExtraction, DocumentItem, ItemKind
from app.domain.record import Fact, FieldStatus, TurnSource
from app.domain.report import builder
from app.domain.report.safety import find_unsupported_assertions
from tests.conftest import FROZEN_NOW, HOSPITAL_ID

GOLDEN = Path(__file__).parent / "golden"
LANGUAGES = ("en", "hi")


def _check_golden(name: str, actual: str) -> None:
    """Compare against the checked-in golden file, writing it on first run."""
    GOLDEN.mkdir(parents=True, exist_ok=True)
    path = GOLDEN / name
    if not path.is_file():
        path.write_text(actual, encoding="utf-8")
        pytest.fail(
            f"wrote a new golden file at {path}. Read it, then re-run — "
            "a golden file nobody looked at asserts nothing."
        )
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"{name} changed. If the change is intended, delete the golden file and "
        "re-run to regenerate it, then read the diff before committing."
    )


@pytest.fixture
async def rendered(
    ingest_service: Any,
    document_service: Any,
    report_service: Any,
    kiosk_payload: dict[str, Any],
    ocr_images: dict[str, bytes],
) -> dict[str, str]:
    """One intake, one prescription, one lab report — rendered in both languages.

    Deliberately the full shape: an unresolved field, a refused field, a
    not-applicable field, a low-confidence OCR value, an out-of-range lab result
    with a printed range, one with no range at all, and a drug interaction.
    A golden file that only covers the happy path is a golden file that never
    catches anything.
    """
    result = await ingest_service.ingest(
        kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
    )
    for fixture in ("prescription_clean", "prescription_lowconf", "lab_report"):
        upload = await document_service.upload(
            hospital_id=HOSPITAL_ID,
            intake_id=result.intake_id,
            content=ocr_images[fixture],
            content_type="image/jpeg",
        )
        await document_service.process(
            hospital_id=HOSPITAL_ID, document_id=upload.document_id
        )

    out: dict[str, str] = {}
    for language in LANGUAGES:
        bundle = await report_service.build(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id, language=language
        )
        out[language] = bundle.text
    return out


class TestGoldenFiles:
    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_matches_the_golden_file(
        self, rendered: dict[str, str], language: str
    ) -> None:
        _check_golden(f"report_{language}.txt", rendered[language])


class TestItIsActuallyDeterministic:
    async def test_rendering_twice_is_byte_identical(
        self, ingest_service: Any, report_service: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        first = await report_service.build(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id, language="en"
        )
        second = await report_service.build(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id, language="en"
        )
        assert first.text == second.text
        assert first.report.model_dump(mode="json") == second.report.model_dump(
            mode="json"
        )

    def test_the_builder_takes_no_clock(self) -> None:
        """Purity, asserted structurally.

        `build` derives its timestamp from the record rather than reading one,
        which is what makes byte-identical rendering possible at all.
        """
        import inspect

        parameters = set(inspect.signature(builder.build).parameters)
        assert "clock" not in parameters
        assert "now" not in parameters

    async def test_fact_order_does_not_depend_on_insertion_order(
        self, ingest_service: Any, report_service: Any, kiosk_payload: dict[str, Any]
    ) -> None:
        """Shuffling the payload's fields must not shuffle the report.

        JSON objects have no guaranteed order, and a device that serialises its
        fields differently after a firmware update must not produce a different
        document.
        """
        shuffled = {
            **kiosk_payload,
            "fields": dict(reversed(list(kiosk_payload["fields"].items()))),
        }
        first = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        text_a = (
            await report_service.build(
                hospital_id=HOSPITAL_ID, intake_id=first.intake_id, language="en"
            )
        ).text

        second_payload = {
            **shuffled,
            "intake_id": "8d1d8b0e-3d6f-4a52-9b1a-2f0a0c0d0e02",
        }
        second = await ingest_service.ingest(
            second_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        text_b = (
            await report_service.build(
                hospital_id=HOSPITAL_ID, intake_id=second.intake_id, language="en"
            )
        ).text

        assert text_a.replace(first.intake_id, "") == text_b.replace(
            second.intake_id, ""
        )


class TestTheReportSaysNothingItShouldNot:
    @pytest.mark.parametrize("language", LANGUAGES)
    async def test_no_forbidden_assertion_appears(
        self, rendered: dict[str, str], language: str
    ) -> None:
        """No diagnosis, no interpretation, no advice.

        The report is a template, so this cannot happen by accident. The scan
        stays as a standing assertion for the day somebody wires a model into
        this path.
        """
        assert find_unsupported_assertions(rendered[language]) == ()

    async def test_the_disclaimer_is_on_every_report(
        self, rendered: dict[str, str], content: Any
    ) -> None:
        """The sentence that keeps a draft intake from reading as an opinion."""
        for language in LANGUAGES:
            templates = content.templates.require(language)
            assert templates.text("header_disclaimer") in rendered[language]
            assert templates.text("footer_disclaimer") in rendered[language]

    async def test_the_patients_own_words_are_not_translated(
        self, rendered: dict[str, str]
    ) -> None:
        """Verbatim, in the script they were spoken in — in both reports.

        The English report shows the Hindi utterance beside the normalised term.
        Translating it would put words in the patient's mouth in a document
        attributed to them.
        """
        for language in LANGUAGES:
            assert "पेट में दर्द" in rendered[language]
            assert "तीन दिन से" in rendered[language]

    async def test_the_unresolved_field_is_on_both_reports(
        self, rendered: dict[str, str]
    ) -> None:
        for language in LANGUAGES:
            assert "severity" in rendered[language].lower() or "तीव्रता" in (
                rendered[language]
            )

    async def test_the_low_confidence_dose_is_marked_and_shows_its_raw_text(
        self, rendered: dict[str, str], content: Any
    ) -> None:
        """The `900.2`-for-`100.2` case.

        Marked, and printed beside what the OCR pass actually read, so a
        physician can compare it against the paper in the patient's hand.
        """
        for language in LANGUAGES:
            marker = content.templates.require(language).text("verify_marker")
            assert marker in rendered[language]
            assert "900.2" in rendered[language]

    async def test_a_lab_value_with_no_printed_range_is_not_flagged(
        self, rendered: dict[str, str], content: Any
    ) -> None:
        """Serum ferritin has no printed range on the fixture report.

        It must say so and stop. Comparing it against a range from anywhere else
        would be manufacturing a clinical finding out of a formatting gap.
        """
        for language in LANGUAGES:
            templates = content.templates.require(language)
            assert templates.text("range_unavailable") in rendered[language]
        english = rendered["en"]
        ferritin_line = next(
            line for line in english.splitlines() if "ferritin" in line.lower()
        )
        assert "below the reference range" not in ferritin_line
        assert "above the reference range" not in ferritin_line

    async def test_out_of_range_values_are_stated_descriptively(
        self, rendered: dict[str, str]
    ) -> None:
        """Haemoglobin 9.8 against a printed 12.0–15.0.

        The report says where the number sits and nothing else — no condition
        named, no cause suggested, no action recommended.
        """
        english = rendered["en"]
        haemoglobin = next(
            line for line in english.splitlines() if "haemoglobin" in line.lower()
        )
        assert "below the reference range printed on this report" in haemoglobin
        assert "anaemia" not in haemoglobin.lower()
        assert find_unsupported_assertions(haemoglobin) == ()


class TestTheDocumentTimeline:
    """Every uploaded document is placed in time, or its missing date is named."""

    def _section(self, text: str, title: str) -> list[str]:
        lines = text.splitlines()
        start = lines.index(title)
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i] and lines[i].isupper()),
            len(lines),
        )
        return [ln.strip().lstrip("- ") for ln in lines[start + 1 : end] if ln.strip()]

    async def test_a_dated_document_states_how_long_before_the_intake(
        self, rendered: dict[str, str]
    ) -> None:
        rows = self._section(rendered["en"], "DOCUMENT TIMELINE")
        dated = [r for r in rows if "day(s) before this intake" in r]
        assert dated, rows
        assert all("not necessarily today" in r for r in dated)

    async def test_an_undated_document_is_named_as_its_own_problem(
        self, rendered: dict[str, str]
    ) -> None:
        """The low-confidence prescription fixture carries no legible date."""
        rows = self._section(rendered["en"], "DOCUMENT TIMELINE")
        undated = [r for r in rows if "no legible date" in r]
        assert undated, rows
        assert "treat every value read from it as historical" in undated[0]

    async def test_the_timeline_renders_in_hindi_too(
        self, rendered: dict[str, str]
    ) -> None:
        rows = self._section(rendered["hi"], "दस्तावेज़ समयरेखा")
        assert rows
        assert any("पठनीय तिथि नहीं" in r for r in rows)


class TestChiefComplaintPromotion:
    """A `chief_complaint` field renders under CHIEF COMPLAINT regardless of
    which section its own content carries it in — 2026-09-11.

    The kiosk's core `chief_complaint` field already sets `Section
    .CHIEF_COMPLAINT` itself; this is for content built on a different question
    set, where the field is namespaced (`routing.chief_complaint`) and its
    section is whatever the routing questions carry, which is HPI on the
    deployed app bundle. A physician opening the report to an empty header
    while the actual complaint sits a section down reads as "no complaint was
    taken", not as a content quirk.
    """

    def _fact(self, field_id: str, section: Section) -> Fact:
        return Fact(
            fact_id="f1",
            field_id=field_id,
            status=FieldStatus.ANSWERED,
            source=TurnSource(turn_id=1),
            section=section,
            recorded_at=FROZEN_NOW,
        )

    def test_a_namespaced_chief_complaint_field_is_promoted(self) -> None:
        fact = self._fact("routing.chief_complaint", Section.HPI)
        assert builder._effective_section(fact) is Section.CHIEF_COMPLAINT

    def test_the_bare_field_needs_no_promotion(self) -> None:
        fact = self._fact("chief_complaint", Section.CHIEF_COMPLAINT)
        assert builder._effective_section(fact) is Section.CHIEF_COMPLAINT

    def test_a_field_that_merely_contains_the_word_is_not_promoted(self) -> None:
        """`routing.complaints` (plural) is the multi-select of complaint
        areas used for triage, not the chief complaint itself. A substring
        match would have promoted it too."""
        fact = self._fact("routing.complaints", Section.HPI)
        assert builder._effective_section(fact) is Section.HPI


class TestUnclassifiedDocumentText:
    """`OTHER` items — text the OCR pass read but did not classify — are shown
    plainly as unclassified, never filed as a prior investigation.

    2026-09-11: a bed-rest certificate's own boilerplate (doctor's name,
    signature date, the patient's father's name) came back as `other` items
    and were dumped into PRIOR INVESTIGATIONS by the old catch-all, which read
    as ten fabricated investigations. They now land in the document-notes area
    that already carries "this document did not come through cleanly", plainly
    marked as unclassified.
    """

    def _extraction(self, *items: DocumentItem) -> DocumentExtraction:
        return DocumentExtraction(document_id="doc_1", items=list(items))

    def _other(self, item_id: str, raw_text: str) -> DocumentItem:
        return DocumentItem(
            item_id=item_id,
            kind=ItemKind.OTHER,
            raw_text=raw_text,
            page=1,
            confidence=0.9,
        )

    async def test_an_other_item_does_not_appear_in_investigations(
        self, content: Any
    ) -> None:
        templates = content.templates.require("en")
        extraction = self._extraction(self._other("i1", "Father's Name"))
        grouped = builder._document_lines([extraction], templates)
        assert Section.INVESTIGATIONS not in grouped

    async def test_an_other_item_is_shown_as_unclassified_instead(
        self, content: Any
    ) -> None:
        templates = content.templates.require("en")
        extraction = self._extraction(self._other("i1", "Father's Name"))
        lines = builder._unclassified_lines([extraction], templates)
        assert len(lines) == 1
        assert "Father's Name" in lines[0].text
        assert "doc_1" in lines[0].text

    async def test_a_real_lab_result_still_lands_in_investigations(
        self, content: Any
    ) -> None:
        """The fix removes the OTHER catch-all, not the mapping every other
        kind still has."""
        from app.domain.documents.extraction import LabResult

        templates = content.templates.require("en")
        lab_item = DocumentItem(
            item_id="i1",
            kind=ItemKind.LAB_RESULT,
            raw_text="Hb 9.8",
            page=1,
            confidence=0.9,
            lab_result=LabResult(analyte="Haemoglobin", value=9.8, unit="g/dL"),
        )
        grouped = builder._document_lines([self._extraction(lab_item)], templates)
        assert Section.INVESTIGATIONS in grouped

    async def test_the_aadhaar_fixture_reads_redacted_and_unclassified(
        self,
        ingest_service: Any,
        document_service: Any,
        report_service: Any,
        kiosk_payload: dict[str, Any],
        ocr_images: dict[str, bytes],
    ) -> None:
        """End to end: the document that used to leak an Aadhaar-shaped number
        into the report now reads redacted, and lands as unclassified text
        rather than a phantom investigation."""
        result = await ingest_service.ingest(
            kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
        )
        upload = await document_service.upload(
            hospital_id=HOSPITAL_ID,
            intake_id=result.intake_id,
            content=ocr_images["contains_aadhaar"],
            content_type="image/jpeg",
        )
        await document_service.process(
            hospital_id=HOSPITAL_ID, document_id=upload.document_id
        )
        bundle = await report_service.build(
            hospital_id=HOSPITAL_ID, intake_id=result.intake_id, language="en"
        )
        text = bundle.text
        assert "4321 8765 2108" not in text
        assert "9876543210" not in text

        investigations = self._section_of(text, "PRIOR INVESTIGATIONS")
        assert not any("Aadhaar" in row or "Mobile" in row for row in investigations)

    @staticmethod
    def _section_of(text: str, title: str) -> list[str]:
        lines = text.splitlines()
        start = lines.index(title)
        end = next(
            (i for i in range(start + 1, len(lines)) if lines[i] and lines[i].isupper()),
            len(lines),
        )
        return lines[start + 1 : end]
