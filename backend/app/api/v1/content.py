"""The question content bundle — 2/3 §4, §12.

One endpoint, serving the artefact the Jetson and the patient app both walk. It
is the contract between three parties, so it is versioned like one and cached
like a static asset.

**Unauthenticated, deliberately.** The bundle is the questions an OPD asks. It
contains no patient data, and requiring a credential to fetch it would mean the
app cannot show a sign-in screen in the patient's own language before the
patient has signed in. `tests/api/test_roles.py` lists it among the routes that
are open on purpose, so the decision is recorded where somebody would look.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Response, status

from app.api.deps import ContentDep
from app.core.logging import get_logger
from app.domain.questions.bundle import canonical_json, compile_bundle, etag_for
from app.normalize.registry import supported_versions

logger = get_logger(__name__)

router = APIRouter(prefix="/content", tags=["content"])


def _schema_version() -> str:
    """The record contract this bundle's answers are meant to produce.

    Read from the normalizer registry rather than configured separately: the
    bundle promises a schema the backend can actually accept, and two sources of
    truth for that would eventually disagree.
    """
    return supported_versions()[-1]


@router.get(
    "/bundle",
    summary="The question content the kiosk and the patient app walk",
    response_model=None,
)
async def bundle(
    content: ContentDep,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    """The current bundle, or `304` when the client already has it.

    The `ETag` is a hash of the body rather than the version string, so an edit
    to a prompt that nobody remembered to bump `content_version` for still
    invalidates every cached copy. The version is what a human reads in a
    changelog; the ETag is what is actually enforced.

    80 KB of Devanagari and English prompts on what may be a patient's mobile
    data, fetched on every app launch. The 304 is not an optimisation detail —
    it is the difference between an app that opens instantly on a bad connection
    and one that does not.
    """
    compiled = compile_bundle(content.questions, schema_version=_schema_version())
    tag = etag_for(compiled)

    if if_none_match and tag in {t.strip() for t in if_none_match.split(",")}:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": tag})

    body = canonical_json(compiled)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "ETag": tag,
            # Revalidate every time rather than trusting a max-age. A stale
            # red-flag rule is a safety problem, and the 304 makes revalidation
            # nearly free.
            "Cache-Control": "no-cache, must-revalidate",
            "X-Content-Version": compiled["content_version"],
        },
    )


@router.get(
    "/bundle/version",
    summary="The current content version, without downloading the bundle",
)
async def bundle_version(content: ContentDep) -> dict[str, Any]:
    """A cheap check for a client deciding whether to refresh on a metered
    connection."""
    compiled = compile_bundle(content.questions, schema_version=_schema_version())
    return {
        "content_version": compiled["content_version"],
        "schema_version": compiled["schema_version"],
        "bundle_format": compiled["bundle_format"],
        "etag": etag_for(compiled),
        "languages": compiled["languages"],
    }


@router.get(
    "/consent",
    summary="The consent notice a patient is shown before intake",
)
async def consent_notice(
    content: ContentDep,
    source: Annotated[str, Query()] = "kiosk",
) -> dict[str, Any]:
    """The purposes, in every language they are authored in — §11, DPDP.

    Unauthenticated for the same reason the bundle is: a patient must be able to
    read what they are agreeing to before they have agreed to anything, and
    certainly before they have signed in.

    `source` filters purposes by where they apply. `raw_audio_retention` is
    annotated `applies_to: [kiosk]` in the content, because the patient app has
    no microphone — asking for consent to retain audio it cannot capture would
    produce an artefact describing something that never happened, and the DPDP
    obligation is to be able to show exactly what the patient agreed to.
    """
    artefact = content.consent
    purposes = [
        {
            "code": purpose["code"],
            "required": bool(purpose.get("required", False)),
            "default_granted": bool(purpose.get("default_granted", True)),
            "label": dict(purpose.get("label", {})),
            "description": dict(purpose.get("description", {})),
        }
        for purpose in artefact.get("purposes", [])
        if source in purpose.get("applies_to", [source])
    ]
    return {
        "consent_version": str(artefact.get("version", "1")),
        "effective_from": str(artefact.get("effective_from", "")),
        "purposes": purposes,
    }
