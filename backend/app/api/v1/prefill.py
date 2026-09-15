"""Mid-intake prefill — suggesting answers from the patient's own words."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.auth import RequireIntakeSubmitter
from app.api.deps import PrefillServiceDep
from app.schemas.api import PrefillRequest, PrefillResponse, PrefillSuggestionOut

router = APIRouter(prefix="/intakes", tags=["prefill"])


@router.post(
    "/{intake_id}/prefill",
    response_model=PrefillResponse,
    summary="Suggest answers to upcoming questions from a free-text one",
)
async def prefill(
    intake_id: str,
    principal: RequireIntakeSubmitter,
    service: PrefillServiceDep,
    request: PrefillRequest,
) -> PrefillResponse:
    """Best-effort only. The interview does not wait on this to move the
    patient to the next question, and a failure or an empty result here
    changes nothing about how it proceeds — the questions are simply asked as
    they always were.

    `intake_id` scopes the call to one interview the same way every other
    `/intakes/{intake_id}/...` route does; nothing is read from or written to
    the record here, and no clinical text this call carries is stored or
    logged beyond the count of questions asked and suggested (§ see
    `app/services/prefill.py`). A suggestion becomes part of the record only
    when the patient accepts it on their own screen, at which point it travels
    through `POST /intakes/ingest` exactly like any other answer —
    indistinguishable from one the patient typed or tapped unprompted.
    """
    outcome = await service.suggest(
        free_text=request.free_text,
        questions=[q.model_dump() for q in request.questions],
    )
    return PrefillResponse(
        enabled=outcome.reason != "disabled",
        suggestions=[
            PrefillSuggestionOut(field_id=field_id, kind=body["kind"], value=body["value"])
            for field_id, body in outcome.suggestions.items()
        ],
    )
