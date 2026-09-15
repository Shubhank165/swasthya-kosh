"""Provider protocols.

Every place a cloud service could plug in is a Protocol here, implemented in
this build by a deterministic mock and by one real adapter that is config-gated.
When Vertex credentials arrive, or a hospital insists nothing leaves the
building, the change is an environment variable — nothing above `app/adapters/`
knows which implementation is live.

Note what is deliberately **not** a protocol. There is no `NextQuestionProvider`,
no `RedFlagClassifier`, no `ReportWriter`. Question selection and red-flag
evaluation live on the Jetson, permanently; the report is a template,
permanently. A protocol here would be an invitation to wire a model into a path
that must not have one.

`TimelineProvider` and `PrefillProvider` are the two additions to that list, and
each distinction has to be written down rather than assumed.

`TimelineProvider` **selects and dates events that already exist in stored
records**. It authors no prose: `validate.py` takes each event's label from the
candidate it claims to be and throws the model's wording away. It states no
diagnosis, its output renders through the same templates as every other line,
and the same `safety.py` scan reads it — which matters, because those are the
only report lines whose contents a model had any say in, and that scan is
exactly what it exists for.

`PrefillProvider` **suggests values for structured questions the app has not
yet put**, from the free text the patient has already typed or dictated earlier
in this same interview. It is not a `NextQuestionProvider`: it never decides
which question is asked or skipped — the walker still plans and puts every
question exactly as it would with no provider configured at all. What it
changes is only what is pre-filled on a screen the patient has not seen yet, and
every suggestion is re-validated against that question's own options, range and
type in `app/services/prefill.py` before the app ever receives it. A suggestion
the patient never confirms is never recorded — see that module for the rest of
the argument.

The difference from a `ReportWriter` is not one of degree, for either addition.
A writer would decide what the document *says*; a timeline decides which of the
things already on the record are worth a physician's attention today, and a
prefill decides what a patient might tap next — both leave the actual answer to
pure code and, in the prefill case, to the patient's own action.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.documents.extraction import DocumentExtraction
from app.domain.record import DocumentKind
from app.domain.timeline.model import TimelineDraft, TimelineRequest


class OCRProvider(Protocol):
    """Reads an uploaded prescription, report or discharge summary.

    `hint` is what the uploader claimed the document is. The provider may
    disagree — the classification it returns is what counts.
    """

    name: str

    async def read(
        self, image: bytes, *, document_id: str, hint: DocumentKind | None = None
    ) -> DocumentExtraction: ...


class RepairProvider(Protocol):
    """Restructures a malformed kiosk payload into the target schema.

    **The only place a language model touches clinical input.** It restructures;
    it does not extract, infer or interpret. See `app/services/repair.py` for the
    instruction it is given and the re-validation it is subject to.
    """

    name: str

    async def repair(
        self, payload: dict[str, Any], *, schema: dict[str, Any], errors: list[dict[str, Any]]
    ) -> dict[str, Any] | None: ...


class TimelineProvider(Protocol):
    """Selects which prior events relate to today's complaint.

    Returns `None` as a normal outcome — unavailable, unconfigured, or nothing
    worth selecting — mirroring `RepairProvider`. The caller falls back to the
    deterministic timeline, which is a complete dated history rather than a
    degraded one, so a provider being down costs relevance filtering and not the
    feature.
    """

    name: str

    async def summarise(self, request: TimelineRequest) -> TimelineDraft | None: ...


class PrefillProvider(Protocol):
    """Suggests values for upcoming structured questions from free text.

    Given the patient's own free-text answer and a list of questions the walker
    has not yet put, returns raw suggestion items keyed by `field_id` — never
    more fields than were asked about, though `app/services/prefill.py` checks
    that regardless of what the provider claims. Returns `None` on any failure,
    mirroring `RepairProvider`: an unusable suggestion set is an expected
    outcome, and the caller's fallback is simply to ask the question, which is
    exactly what would have happened with no provider configured at all.
    """

    name: str

    async def suggest(
        self, *, free_text: str, questions: list[dict[str, Any]]
    ) -> dict[str, Any] | None: ...


class ABHAProvider(Protocol):
    """ABHA identity verification.

    ABHA is an identity and consent-linking mechanism, not a database of the
    patient's history, and it is never required for basic intake.
    """

    name: str

    async def verify(self, abha_address: str) -> dict[str, Any] | None: ...


class ObjectStore(Protocol):
    """Where document images live.

    Never public. Reads go through a signed URL with a short expiry, because a
    document link that outlives the consultation is a document link that ends up
    in a WhatsApp group.
    """

    name: str

    async def put(self, key: str, data: bytes, *, content_type: str) -> str: ...

    async def get(self, key: str) -> bytes: ...

    async def signed_url(self, key: str, *, ttl_seconds: int) -> str: ...

    async def delete(self, key: str) -> None: ...


class OTPSender(Protocol):
    """Delivers a one-time code to a phone — 2/3 §7.1.

    Behind a protocol like every other outside-the-process dependency, so the
    demo and the whole test suite run without an SMS gateway account and without
    a rupee of spend.
    """

    name: str
    #: True when the sender does not actually deliver anything, so the caller
    #: may return the code in the response for a local demo. `PatientAuthService`
    #: additionally refuses to do that outside development, so a misconfigured
    #: production deployment cannot leak live codes through the API.
    reveals_code: bool

    async def send(self, *, phone: str, code: str) -> None: ...
