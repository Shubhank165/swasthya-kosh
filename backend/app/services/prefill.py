"""The prefill path — suggesting, from a patient's own words, answers to
questions the interview has not asked yet.

```
free text + upcoming questions -> provider -> per-field validation -> suggestions
```

The provider's whole job is to structure a guess; this module's job is to
refuse the ones it should not have made. Every suggestion is checked against
the very question it claims to answer before this function returns it: a
choice must name a real option, a number must fall inside the question's own
range, a duration must carry one of the units the app recognises. The
instruction given to a model is not evidence — the same reasoning
`app/services/repair.py` gives for re-validating regardless of what the model
claims.

**A suggestion is not an answer.** Nothing this module returns is ever written
to an intake record. It reaches the kiosk as a pre-filled value on a screen the
patient has not seen yet, and only the patient's own tap or Continue turns it
into a recorded fact — indistinguishable on the record from any other answer.
That is the opposite of how `repair` marks its own output: a repaired field is
stamped `repaired = True` forever, because a machine restructured it and nobody
confirmed it did so correctly. A suggestion the patient accepted carries no
such mark, because by the time it is accepted it is the patient's answer, not
the model's guess.

If prefill is disabled, misconfigured, or the provider fails outright, the
outcome is an empty suggestion set — never an exception. A patient who gets no
suggestions is simply asked every question, which is exactly what happened
before this feature existed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.adapters.protocols import PrefillProvider
from app.core.logging import get_logger

logger = get_logger(__name__)

__all__ = ["PENDING_TYPES", "PrefillOutcome", "PrefillService", "pending_payload", "suggest"]

#: Answer types eligible for a suggestion. `free_text` is the source, not a
#: target — prefilling a descriptive question from itself is not this feature —
#: and `date` is excluded because none of the dates this interview asks for
#: ("when did the surgery happen", "when did the last period start") are ones a
#: wrong guess is safe to be wrong about.
PENDING_TYPES: frozenset[str] = frozenset(
    {"single_choice", "multi_choice", "yes_no_unknown", "number", "scale", "duration"}
)

#: `answer_type` -> the `AnswerValue.kind` string a valid suggestion for it must
#: carry. Mirrors `app/lib/content/answer.dart`'s `answerValueFromDraft`, which
#: is what turns this service's output back into a value on the app side.
_EXPECTED_KIND: Mapping[str, str] = {
    "single_choice": "coded",
    "multi_choice": "coded_list",
    "yes_no_unknown": "bool",
    "number": "number",
    "scale": "scale",
    "duration": "duration",
}

#: The units `DurationAnswer` on the app side offers. Anything else is not a
#: duration this build can render, so a suggestion carrying one is dropped
#: rather than passed through unrecognised.
_DURATION_UNITS = frozenset({"hour", "day", "week", "month", "year"})


@dataclass(frozen=True, slots=True)
class PrefillOutcome:
    """What the prefill path produced."""

    #: `field_id` -> `{"kind": ..., "value": ...}`, one entry per field the
    #: provider suggested *and* this service could validate.
    suggestions: Mapping[str, dict[str, Any]] = field(default_factory=dict)
    #: `ok` | `disabled` | `no_free_text` | `no_pending_questions` | `provider_failed`
    reason: str = "ok"


def pending_payload(question: Mapping[str, Any]) -> dict[str, Any]:
    """The minimal shape a provider needs for one question.

    No prompts in languages the provider was not asked about, no clinical
    framing beyond what the question itself already carries.
    """
    body: dict[str, Any] = {
        "field_id": question["field_id"],
        "answer_type": question["answer_type"],
        "prompt": question.get("prompt") or "",
    }
    for key in ("options", "unit", "min", "max"):
        value = question.get(key)
        if value is not None:
            body[key] = value
    return body


async def suggest(
    *,
    free_text: str,
    questions: Sequence[Mapping[str, Any]],
    provider: PrefillProvider | None,
) -> PrefillOutcome:
    """Suggest values for the eligible entries of `questions`, from `free_text`.

    Never raises: an unusable suggestion set is an expected outcome here, just
    as a failed repair is in `repair.attempt` — the caller's fallback in every
    branch is simply to ask the question normally.
    """
    if provider is None:
        return PrefillOutcome(reason="disabled")
    if not free_text or not free_text.strip():
        return PrefillOutcome(reason="no_free_text")

    eligible = {
        q["field_id"]: q
        for q in questions
        if q.get("field_id") and q.get("answer_type") in PENDING_TYPES
    }
    if not eligible:
        return PrefillOutcome(reason="no_pending_questions")

    try:
        raw = await provider.suggest(
            free_text=free_text,
            questions=[pending_payload(q) for q in eligible.values()],
        )
    except Exception:
        logger.warning("prefill_call_failed", provider=provider.name)
        return PrefillOutcome(reason="provider_failed")

    if raw is None:
        return PrefillOutcome(reason="provider_failed")

    validated: dict[str, dict[str, Any]] = {}
    for field_id, body in raw.items():
        question = eligible.get(field_id)
        # Never a field beyond the ones this call actually asked about — the
        # same reasoning `repair`'s identity check gives for a model that
        # writes more than it was shown.
        if question is None or not isinstance(body, Mapping):
            continue
        value = _validate_one(question, body)
        if value is not None:
            validated[field_id] = value

    logger.info(
        "prefill_suggested",
        provider=provider.name,
        requested=len(eligible),
        suggested=len(validated),
    )
    return PrefillOutcome(suggestions=validated, reason="ok")


def _validate_one(
    question: Mapping[str, Any], body: Mapping[str, Any]
) -> dict[str, Any] | None:
    """One suggestion, checked against the question it claims to answer.

    Returns `None` for anything that does not check out completely — there is
    no partial credit and no clamping a number into range, because a clamped
    value is a value the patient did not say and the model did not (correctly)
    suggest either.
    """
    answer_type = question["answer_type"]
    expected_kind = _EXPECTED_KIND.get(answer_type)
    if body.get("kind") != expected_kind:
        return None

    if answer_type == "single_choice":
        value = body.get("value")
        options = question.get("options") or []
        if not isinstance(value, str) or value not in options:
            return None
        return {"kind": "coded", "value": value}

    if answer_type == "multi_choice":
        codes = body.get("codes")
        options = question.get("options") or []
        if not isinstance(codes, list) or not codes:
            return None
        cleaned = [c for c in codes if isinstance(c, str) and c in options]
        if len(cleaned) != len(codes):
            # Any code that is not a real option makes the whole suggestion
            # untrustworthy, not just that one entry.
            return None
        return {"kind": "coded_list", "value": cleaned}

    if answer_type == "yes_no_unknown":
        parsed = _as_bool(body.get("value"))
        if parsed is None:
            return None
        return {"kind": "bool", "value": parsed}

    if answer_type in ("number", "scale"):
        value = _as_float(body.get("value"))
        if value is None:
            return None
        minimum = question.get("min")
        maximum = question.get("max")
        if minimum is not None and value < float(minimum):
            return None
        if maximum is not None and value > float(maximum):
            return None
        return {"kind": answer_type, "value": value}

    if answer_type == "duration":
        n = _as_float(body.get("value"))
        unit = body.get("unit")
        if n is None or unit not in _DURATION_UNITS:
            return None
        return {"kind": "duration", "value": {"n": n, "unit": unit}}

    return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes"):
            return True
        if lowered in ("false", "no"):
            return False
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


class PrefillService:
    """Binds a provider once per process, so this fits the same per-request
    dependency shape as every other service in `app/api/deps.py`."""

    def __init__(self, provider: PrefillProvider | None) -> None:
        self._provider = provider

    async def suggest(
        self, *, free_text: str, questions: Sequence[Mapping[str, Any]]
    ) -> PrefillOutcome:
        return await suggest(free_text=free_text, questions=questions, provider=self._provider)
