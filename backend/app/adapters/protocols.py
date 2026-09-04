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
"""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.documents.extraction import DocumentExtraction
from app.domain.record import DocumentKind


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
