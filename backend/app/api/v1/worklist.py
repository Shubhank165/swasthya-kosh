"""Worklist and alert acknowledgement — §8.4, §10."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.auth import RequireAdmin, RequireStaff
from app.api.deps import ClockDep, MetricsRepoDep, SettingsDep, WorklistServiceDep
from app.api.serialise import worklist_out
from app.domain.worklist import WorklistState
from app.schemas.api import (
    AcknowledgeRequest,
    AcknowledgeResponse,
    AlertListOut,
    AlertOut,
    CorrectionRateOut,
    MetricsOut,
    WorklistOut,
)

router = APIRouter(tags=["worklist"])


@router.get(
    "/worklist",
    response_model=WorklistOut,
    summary="Intakes waiting for a doctor, in arrival order",
)
async def worklist(
    principal: RequireStaff,
    service: WorklistServiceDep,
    settings: SettingsDep,
    department: Annotated[str | None, Query()] = None,
    state: Annotated[list[WorklistState] | None, Query()] = None,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> WorklistOut:
    """The ordered list for a department.

    Arrival order. A fired red-flag criterion pulls the row into
    `pending_alerts` so it cannot be scrolled past, but it does **not** move the
    intake up the list — reordering a waiting room on a machine's reading of a
    symptom is a triage decision, and this system does not make those.

    `state` narrows the list; `total` still counts the whole window, so a filter
    that hides thirty patients says so rather than making the department look
    quiet. `pending_alerts` is **never** filtered — an unacknowledged red flag
    that a dropdown could hide is a red flag the dashboard has failed to raise.
    """
    result = await service.worklist(
        hospital_id=principal.hospital_id,
        department_code=department,
        window=timedelta(hours=hours),
    )
    if state:
        wanted = set(state)
        result = result.model_copy(
            update={"entries": tuple(e for e in result.entries if e.state in wanted)}
        )
    return worklist_out(result, demo=settings.demo_mode)


@router.get(
    "/alerts",
    response_model=AlertListOut,
    summary="Red-flag criteria that fired, unacknowledged first",
)
async def alerts(
    principal: RequireStaff,
    service: WorklistServiceDep,
    settings: SettingsDep,
    clock: ClockDep,
    acknowledged: Annotated[bool | None, Query()] = None,
    department: Annotated[str | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> AlertListOut:
    """The triage view — §4.3.

    Every alert carries the rule's own fixed wording and the answers that met
    it. **Never a condition name**: the device screened a questionnaire, it did
    not examine a patient, and a label that named a diagnosis would be a
    diagnosis this system is not permitted to make.

    Acknowledging is a separate `POST` and escalation is a third thing that
    happens outside this API. Nothing here collapses the two.
    """
    rows = await service.alerts(
        hospital_id=principal.hospital_id,
        acknowledged=acknowledged,
        department_code=department,
        window=timedelta(days=days),
    )
    return AlertListOut(
        alerts=[AlertOut.model_validate(row) for row in rows],
        unacknowledged=sum(1 for row in rows if row["acknowledged_by"] is None),
        generated_at=clock.now(),
        demo=settings.demo_mode,
    )


@router.post(
    "/alerts/{intake_id}/acknowledge",
    response_model=AcknowledgeResponse,
    summary="Acknowledge a red-flag event",
)
async def acknowledge(
    intake_id: str,
    principal: RequireStaff,
    service: WorklistServiceDep,
    request: AcknowledgeRequest,
) -> AcknowledgeResponse:
    """Record that a person has seen an alert.

    Acknowledgement is a record of a human having looked, and nothing else. It
    escalates nothing, reorders nothing and notifies nobody automatically — what
    happens next is the acknowledging clinician's decision, made outside this
    system.

    A second acknowledgement is a 409 rather than a silent success: two people
    each assuming the other has seen it is the failure worth being noisy about.
    """
    result = await service.acknowledge(
        hospital_id=principal.hospital_id,
        intake_id=intake_id,
        rule_id=request.rule_id,
        actor_id=principal.user_id,
        actor_role=principal.role.value,
        note=request.note,
    )
    return AcknowledgeResponse.model_validate(result)


@router.get(
    "/metrics/ingest",
    response_model=MetricsOut,
    summary="Ingest quality counters",
)
async def metrics(
    principal: RequireStaff,
    repository: MetricsRepoDep,
) -> MetricsOut:
    """How often the repair path ran.

    `repair_rate` counts intakes whose payload failed its contract and had to be
    restructured by a model. It should fall as the Jetson's extractor improves,
    and a number that moves in the right direction over a fortnight is a better
    argument than any slide.
    """
    return MetricsOut.model_validate(
        await repository.repair_rate(hospital_id=principal.hospital_id)
    )


@router.get(
    "/metrics/correction-rate",
    response_model=CorrectionRateOut,
    summary="How often a physician corrected the pipeline",
)
async def correction_rate(
    principal: RequireAdmin,
    repository: MetricsRepoDep,
    settings: SettingsDep,
) -> CorrectionRateOut:
    """The extraction-quality metric — §6, §B3.

    Admin-scoped, not because it is sensitive but because it is a claim about
    the system rather than about a patient, and the person making that claim on
    a slide should be the person who can see how it was computed.

    It replaces the figures the shelved evaluation harness used to produce.
    Those measured question selection, which now runs on the Jetson, so they no
    longer describe anything this backend does — and none of them may be quoted
    until this number has data behind it.
    """
    return CorrectionRateOut(
        **await repository.correction_rate(hospital_id=principal.hospital_id),
        demo=settings.demo_mode,
    )
