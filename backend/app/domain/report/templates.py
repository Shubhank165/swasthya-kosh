"""Report templates, one set per language.

Templates are **written** per language, not translated at runtime. A machine
translation of "not established" that lands on "अनुपस्थित" — absent — would
convert an unasked question into a denial, in a document a physician acts on.
So `clinical/report_templates/hi/` is authored Hindi, reviewed as Hindi, and the
loader refuses a language whose file is missing rather than falling back to
English silently.

The patient's own words are never translated. They are printed verbatim, in the
script they were spoken in, beside the normalised term.

This module holds the *shape* of a template set and its validation. The strings
live in `clinical/report_templates/<lang>/report.yaml`, so a clinician can
review the wording without reading Python.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.domain.clinical.enums import Section

#: Keys every language file must define. A missing key fails the load — a report
#: with an untranslated heading is a report nobody trusts.
REQUIRED_KEYS: tuple[str, ...] = (
    "header_disclaimer",
    "footer_disclaimer",
    "unresolved_title",
    "conflicts_title",
    "safety_title",
    "interactions_title",
    "timeline_title",
    "timeline_dated",
    "timeline_future",
    "timeline_undated",
    "timeline_none",
    "nothing_recorded",
    "nothing_outstanding",
    "no_conflicts",
    "no_alerts",
    "no_interactions",
    "not_established",
    "declined_to_answer",
    "not_applicable",
    "denies",
    "patient_said",
    "repaired_marker",
    "verify_marker",
    "approximate_marker",
    "uncertain_marker",
    "unverified_marker",
    "attendant_marker",
    "conflict_today",
    "conflict_record",
    "conflict_not_mentioned",
    "conflict_resolution",
    "alert_awaiting",
    "alert_acknowledged",
    "document_unprocessed",
    "document_low_confidence",
    "document_rejected",
    "interaction_prompt",
    "range_below",
    "range_above",
    "range_unavailable",
    "demo_banner",
)

#: Section headings. Every section in `SECTION_ORDER` needs one.
REQUIRED_SECTIONS: tuple[Section, ...] = tuple(
    s for s in Section if s is not Section.CONSENT
)


class TemplateError(ValueError):
    """A template set was incomplete or malformed."""


@dataclass(frozen=True, slots=True)
class TemplateSet:
    """One language's report wording."""

    language: str
    strings: Mapping[str, str]
    section_titles: Mapping[Section, str]
    #: Field labels in this language, overlaying the concept registry's English
    #: displays. Optional and deliberately partial: a field with no entry here
    #: falls back to its English display rather than to a machine translation,
    #: because a mistranslated clinical term on a physician report is worse than
    #: an English one a Hindi-speaking clinician can still read.
    labels: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, language: str, raw: Mapping[str, Any]) -> TemplateSet:
        strings_raw = raw.get("strings")
        if not isinstance(strings_raw, Mapping):
            raise TemplateError(f"{language}: 'strings' must be a mapping")
        sections_raw = raw.get("sections")
        if not isinstance(sections_raw, Mapping):
            raise TemplateError(f"{language}: 'sections' must be a mapping")

        strings = {str(k): str(v) for k, v in strings_raw.items()}
        missing = [key for key in REQUIRED_KEYS if key not in strings]
        if missing:
            raise TemplateError(f"{language}: missing template strings {missing}")

        titles: dict[Section, str] = {}
        for key, value in sections_raw.items():
            try:
                titles[Section(str(key))] = str(value)
            except ValueError as exc:
                raise TemplateError(f"{language}: unknown section '{key}'") from exc
        missing_sections = [s.value for s in REQUIRED_SECTIONS if s not in titles]
        if missing_sections:
            raise TemplateError(f"{language}: missing section titles {missing_sections}")

        labels_raw = raw.get("labels") or {}
        if not isinstance(labels_raw, Mapping):
            raise TemplateError(f"{language}: 'labels' must be a mapping")

        return cls(
            language=language,
            strings=strings,
            section_titles=titles,
            labels={str(k): str(v) for k, v in labels_raw.items()},
        )

    def text(self, key: str) -> str:
        try:
            return self.strings[key]
        except KeyError as exc:  # pragma: no cover - REQUIRED_KEYS makes this dead
            raise TemplateError(f"{self.language}: no template string '{key}'") from exc

    def format(self, key: str, **values: object) -> str:
        """A template string with its placeholders filled.

        A placeholder the language file does not carry is a load-time error
        rather than a `KeyError` at 3am during a demo.
        """
        try:
            return self.text(key).format(**values)
        except (KeyError, IndexError) as exc:
            raise TemplateError(
                f"{self.language}: template '{key}' has a placeholder no caller supplied: {exc}"
            ) from exc

    def title(self, section: Section) -> str:
        return self.section_titles.get(section, section.value.replace("_", " ").title())


class TemplateRegistry:
    """Every loaded language.

    `require` raises rather than falling back. A report requested in Hindi and
    silently rendered in English is a report the patient cannot check.
    """

    def __init__(self, sets: Mapping[str, TemplateSet], *, default: str) -> None:
        if default not in sets:
            raise TemplateError(f"default report language '{default}' was not loaded")
        self._sets = dict(sets)
        self._default = default

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._sets))

    @property
    def default_language(self) -> str:
        return self._default

    def get(self, language: str) -> TemplateSet | None:
        return self._sets.get(language)

    def require(self, language: str) -> TemplateSet:
        template = self._sets.get(language)
        if template is None:
            raise TemplateError(
                f"no report template for language '{language}'; "
                f"available: {list(self.languages)}"
            )
        return template

    def resolve(self, language: str | None) -> TemplateSet:
        """The template for `language`, falling back to the default only when no
        language was asked for at all."""
        if language is None:
            return self._sets[self._default]
        return self.require(language)
