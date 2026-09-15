"""Accepting an AYUSH/Prakriti self-report from a patient's own device.

```
patient's answers + the session's identity -> validation -> a new revision
```

**The identity is never in the request.** `hospital_id` and the patient
reference both come from the session token, per decision 21: a patient
submitting a profile is submitting their own, and a body that could name
someone else is a body someone will eventually name someone else in.

**Certainty has a ceiling here and code may not raise it.** Everything this
module writes is `reported` — the patient said it about themselves. Decision 2
allows certainty to increase only by a human act with a name attached, so a
self-report cannot arrive `confirmed` however emphatically it is phrased, and
this module refuses one that claims to.

**The five statuses arrive intact or the submission is refused.** No mapping,
no collapsing, no defaulting an unrecognised status to `answered` — decision 1
exists because that is exactly how "could not say" turns into "no" somewhere
between a kiosk and a physician.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.clock import Clock
from app.core.errors import ValidationError
from app.core.ids import IdFactory
from app.domain.ayush_profile import AyushProfileSnapshot
from app.domain.clinical.enums import Certainty
from app.domain.record import FieldStatus
from app.repositories.ayush_profiles import AyushProfileRepository

#: What a patient may assert about themselves. `confirmed` is absent on
#: purpose: it is a clinician's word, and decision 2 reserves raising certainty
#: to a human act that records who performed it.
_PATIENT_CERTAINTY: frozenset[str] = frozenset(
    {Certainty.REPORTED.value, Certainty.APPROXIMATE.value, Certainty.UNCERTAIN.value}
)

_STATUSES: frozenset[str] = frozenset(status.value for status in FieldStatus)

#: Every field this module may carry. A submission naming anything else is
#: rejected whole rather than filtered: a client sending `general.*` into an
#: AYUSH profile has misunderstood something, and silently dropping the strays
#: would hide it.
_NAMESPACE = "ayush."

#: One patient's constitution is 62 questions today and will not plausibly be
#: thousands. A cap here is what stops a malformed or hostile client writing an
#: unbounded JSON document into a row nobody reads until a physician opens it.
_MAX_ANSWERS = 200


@dataclass(frozen=True, slots=True)
class ProfileSubmission:
    """What was stored, for the response to report back."""

    profile_id: str
    superseded: str | None
    answers_stored: int


def _validate(answers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every answer checked before any of them is written.

    Rejects the whole submission rather than the offending entry. A profile
    that is 61 of 62 questions because one failed silently is a profile whose
    gaps mean two different things — "not asked" and "we dropped it" — and the
    report has no way to tell a physician which.
    """
    if not answers:
        raise ValidationError("a profile with no answers is not a submission")
    if len(answers) > _MAX_ANSWERS:
        raise ValidationError(f"at most {_MAX_ANSWERS} answers per profile")

    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in answers:
        field_id = entry.get("field_id")
        if not isinstance(field_id, str) or not field_id.startswith(_NAMESPACE):
            raise ValidationError(f"field_id must be in the {_NAMESPACE}* namespace")
        if field_id in seen:
            raise ValidationError(f"duplicate field_id: {field_id}")
        seen.add(field_id)

        status = entry.get("status")
        if status not in _STATUSES:
            raise ValidationError(f"unknown status for {field_id}: {status!r}")

        certainty = entry.get("certainty", Certainty.REPORTED.value)
        if certainty not in _PATIENT_CERTAINTY:
            raise ValidationError(
                f"a self-report may not claim certainty {certainty!r} for {field_id}"
            )

        value = entry.get("value")
        # The fact table's own rule, applied at the door: a value belongs to an
        # answered field and to no other status. An `unresolved` field carrying
        # one is a claim about something the patient did not settle.
        if status != FieldStatus.ANSWERED.value and value is not None:
            raise ValidationError(
                f"{field_id} is {status} and may not carry a value"
            )
        if status == FieldStatus.ANSWERED.value and value is None:
            raise ValidationError(f"{field_id} is answered but carries no value")

        original = entry.get("original_text")
        if original is not None and not isinstance(original, str):
            raise ValidationError(f"original_text for {field_id} must be text")

        cleaned.append(
            {
                "field_id": field_id,
                "status": status,
                "certainty": certainty,
                "value": value,
                "original_text": original,
            }
        )
    return cleaned


class AyushProfileService:
    """Stores one patient's module answers as an append-only revision."""

    def __init__(
        self,
        *,
        profiles: AyushProfileRepository,
        clock: Clock,
        ids: IdFactory,
    ) -> None:
        self._profiles = profiles
        self._clock = clock
        self._ids = ids

    async def submit(
        self,
        *,
        hospital_id: str,
        patient_ref_type: str,
        patient_ref_value: str,
        language: str,
        content_version: str | None,
        answers: Sequence[Mapping[str, Any]],
    ) -> ProfileSubmission:
        """Validate and store. Supersedes the patient's current revision."""
        cleaned = _validate(answers)

        current = await self._profiles.current(
            hospital_id=hospital_id,
            patient_ref_type=patient_ref_type,
            patient_ref_value=patient_ref_value,
        )
        profile_id = self._ids.new_id("ayush")
        await self._profiles.add_revision(
            profile_id=profile_id,
            hospital_id=hospital_id,
            patient_ref_type=patient_ref_type,
            patient_ref_value=patient_ref_value,
            language=language,
            content_version=content_version,
            answers=cleaned,
            submitted_at=self._clock.now(),
            supersedes=current.id if current is not None else None,
        )
        return ProfileSubmission(
            profile_id=profile_id,
            superseded=current.id if current is not None else None,
            answers_stored=len(cleaned),
        )

    async def current_snapshot(
        self, *, hospital_id: str, patient_ref_type: str, patient_ref_value: str
    ) -> AyushProfileSnapshot | None:
        """The live revision as a frozen value, or `None`."""
        from app.repositories.ayush_profiles import snapshot_of

        row = await self._profiles.current(
            hospital_id=hospital_id,
            patient_ref_type=patient_ref_type,
            patient_ref_value=patient_ref_value,
        )
        return snapshot_of(row)
