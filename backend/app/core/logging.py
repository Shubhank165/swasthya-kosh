"""Structured logging with a PHI filter.

Invariant 9: logs never contain clinical text. This is enforced here rather than
by convention, because convention fails at 3am during a demo. Every log record
passes through `scrub`, which drops or redacts any field whose key is on the
denylist and redacts free text that looks like a patient utterance.

`tests/safety/test_logging_phi.py` proves it: it writes every kind of clinical
value into a log call and asserts none of it reaches the emitted record.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

#: Keys whose values are clinical text or direct identifiers. Redacted wholesale
#: wherever they appear, at any depth.
DENYLISTED_KEYS: frozenset[str] = frozenset(
    {
        "original_expression",
        "utterance",
        "transcript",
        "transcript_text",
        "answer",
        "answer_text",
        "free_text",
        "text",
        "value",
        "rendered_value",
        "question",
        "prompt",
        "summary",
        "summary_text",
        "report",
        "report_text",
        "narrative",
        "chief_complaint",
        "complaint",
        "diagnosis",
        "medications",
        "medication",
        "allergy",
        "allergies",
        "patient_name",
        "name",
        "phone",
        "phone_number",
        "mobile",
        "address",
        "abha_id",
        "abha_number",
        "aadhaar",
        "email",
        "date_of_birth",
        "dob",
        "document_text",
        "ocr_text",
        "note",
        "notes",
        "reason_text",
        "statement",
        "display",
        "label",
        "guidance",
        "criteria_description",
    }
)

#: Keys that are safe: identifiers, enums, counters, timings. Anything not on
#: this list and not obviously scalar is treated as suspect.
ALLOWLISTED_KEYS: frozenset[str] = frozenset(
    {
        "event",
        "level",
        "timestamp",
        "logger",
        "intake_id",
        "fact_id",
        "ticket_id",
        "queue_id",
        "instance_id",
        "alert_id",
        "document_id",
        "patient_id",
        "user_id",
        "actor_id",
        "concept",
        "concept_id",
        "section",
        "status",
        "state",
        "severity",
        "rule_id",
        "pathway_id",
        "origin",
        "source_type",
        "certainty",
        "temporality",
        "reported_by",
        "confidence",
        "revision",
        "count",
        "duration_ms",
        "token",
        "priority_class",
        "queue_state",
        "intake_state",
        "language",
        "method",
        "path",
        "status_code",
        "idempotency_key",
        "request_id",
        "coverage_percentage",
        "error_code",
    }
)

REDACTED = "[redacted]"

#: A value long enough or word-rich enough to be a sentence a patient said.
#: Deliberately aggressive: a redacted operational string costs a debugging
#: session, a leaked utterance costs a patient's privacy.
_SENTENCE_LIKE = re.compile(r"\S+\s+\S+\s+\S+")
#: Devanagari and other Indic scripts — a patient's own words, always.
_INDIC = re.compile(r"[ऀ-෿]")
_MAX_SAFE_LEN = 64


def _looks_like_clinical_text(value: str) -> bool:
    if _INDIC.search(value):
        return True
    if len(value) > _MAX_SAFE_LEN:
        return True
    return bool(_SENTENCE_LIKE.search(value))


def scrub(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact anything that could be clinical text or an identifier.

    Rules, in order:
      - a denylisted key is redacted whatever its value,
      - a string that reads like a sentence, or contains Indic script, or is long,
        is redacted unless its key is explicitly allowlisted,
      - containers are walked; scalars pass through.
    """
    if key is not None and key.lower() in DENYLISTED_KEYS:
        return REDACTED
    if isinstance(value, str):
        if key is not None and key.lower() in ALLOWLISTED_KEYS:
            return value
        return REDACTED if _looks_like_clinical_text(value) else value
    if isinstance(value, MutableMapping):
        return {k: scrub(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return type(value)(scrub(v, key=key) for v in value) if not isinstance(
            value, set
        ) else {scrub(v, key=key) for v in value}
    return value


def phi_filter(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor. The last line of defence before a record is emitted."""
    return {key: scrub(value, key=str(key)) for key, value in event_dict.items()}


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    """Install the logging pipeline. Idempotent; safe to call from tests."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            # The PHI filter runs last, after every other processor has had its
            # chance to add fields. Nothing may be added after it.
            phi_filter,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """A bound logger. Always use this rather than `logging.getLogger`, so the
    PHI filter cannot be bypassed."""
    return structlog.get_logger(name)
