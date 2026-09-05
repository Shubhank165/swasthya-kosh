"""Compile the question content into the bundle the app and the Jetson walk — 2/3 §4.

Pure, deterministic and byte-stable, for the same reason the FHIR bundle is: the
`ETag` this endpoint serves is a hash of the body, so a bundle that differs
between two identical requests would make every client re-download it on every
launch and defeat the 304 entirely.

**What this is not.** It is not a question engine. Nothing here decides what to
ask next, evaluates a precondition, or fires a red flag. It emits data; the
device that is asking the questions does the asking.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.domain.questions.model import QuestionSet

#: Bumped when the *shape* of the bundle changes in a way an older app cannot
#: read. Distinct from `content_version`, which changes when the questions
#: change, and from `schema_version`, which is the record contract.
BUNDLE_FORMAT_VERSION = "1"


def compile_bundle(question_set: QuestionSet, *, schema_version: str) -> dict[str, Any]:
    """The wire form.

    `branches` maps a chief-complaint value to the ordered `question_id`s that
    complaint adds — the HPI limb, that complaint's red-flag screen, its
    review-of-systems groups, and the general screen. The questions themselves
    live once in `questions`, so a question shared by two complaints is
    downloaded once and rendered identically in both.
    """
    questions = sorted(question_set.all_questions(), key=lambda q: q.question_id)
    return {
        "bundle_format": BUNDLE_FORMAT_VERSION,
        "content_version": question_set.content_version,
        "schema_version": schema_version,
        "languages": list(question_set.languages),
        "sections": list(question_set.sections),
        "core": [q.question_id for q in question_set.core],
        "branches": {
            complaint: [q.question_id for q in group]
            for complaint, group in sorted(question_set.branches.items())
        },
        "ayurveda": [q.question_id for q in question_set.ayurveda],
        # The subset a returning patient is asked again — 2/3 §5 screen 8. A
        # separate list rather than a flag on each question because the app
        # chooses between two plans, and a plan is a list.
        "ayurveda_current_state": [
            q.question_id for q in question_set.ayurveda if q.current_state
        ],
        "questions": [q.as_bundle() for q in questions],
        "red_flag_rules": [r.as_bundle() for r in question_set.red_flags],
    }


def canonical_json(bundle: dict[str, Any]) -> str:
    """Byte-stable serialisation.

    `sort_keys` and a fixed separator, and `ensure_ascii=False` so the Devanagari
    prompts travel as UTF-8 rather than as escape sequences — the bundle is
    roughly a third smaller that way, on a connection that may be a patient's
    mobile data.
    """
    return json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def etag_for(bundle: dict[str, Any]) -> str:
    """A strong ETag over the bundle's bytes.

    Content-derived rather than a version string, so a content edit that
    somebody forgot to bump `content_version` for still invalidates every
    client's cache. The version is what humans read; this is what is enforced.
    """
    digest = hashlib.sha256(canonical_json(bundle).encode("utf-8")).hexdigest()
    return f'"{digest[:32]}"'
