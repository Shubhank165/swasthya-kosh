"""Queue and ticket endpoints.

`POST /tickets/{id}/escalate` is the one that matters most: it takes an alert id
and an acting user, and it refuses without both. There is no endpoint anywhere
that escalates a patient on a machine's judgement.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    Principal,
    PrincipalDep,
    QueueRepoDep,
    QueueServiceDep,
    Role,
    SettingsDep,
    require_roles,
)
from app.api.serialisers import instance_out, queue_out, ticket_out
from app.core.errors import NotFoundError
from app.domain.clinical.enums import IntakeState
from app.domain.queue.entities import SessionName
from app.domain.queue.policies import PatientAttributes
from app.schemas.queue import (
    CancelRequest,
    DashboardOut,
    DeferRequest,
    DepartmentOut,
    EscalateRequest,
    IssueTicketRequest,
    OpenInstanceRequest,
    PauseRequest,
    QueueInstanceOut,
    QueueOut,
    TicketOut,
    TransferRequest,
)
from app.services.queue import require_shadow_mode_guard

router = APIRouter(prefix="/queues", tags=["queues"])
tickets_router = APIRouter(prefix="/tickets", tags=["tickets"])
instances_router = APIRouter(prefix="/queue-instances", tags=["queues"])
departments_router = APIRouter(prefix="/departments", tags=["queues"])


async def _intake_state_for(repo: QueueRepoDep, ticket_id: str) -> IntakeState | None:
    """Read a ticket's intake state through a join.

    Not stored on the ticket: the two state machines are orthogonal, and a
    denormalised copy would be the first place they drift apart.
    """
    ticket = await repo.get_ticket(ticket_id)
    if ticket is None or ticket.intake_id is None:
        return None
    lookup = await repo.intake_states_for((ticket,))
    return lookup.get(ticket.intake_id)


@departments_router.get("", response_model=list[DepartmentOut])
async def list_departments(repo: QueueRepoDep, _: PrincipalDep) -> list[DepartmentOut]:
    return [
        DepartmentOut(code=d.code, name=d.name, facility=d.facility)
        for d in await repo.list_departments()
    ]


@router.get("", response_model=list[QueueOut])
async def list_queues(
    repo: QueueRepoDep,
    _: PrincipalDep,
    department: Annotated[str | None, Query()] = None,
) -> list[QueueOut]:
    return [queue_out(q) for q in await repo.list_queues(department_code=department)]


@router.get("/{queue_id}/instance", response_model=QueueInstanceOut)
async def get_instance(
    queue_id: str,
    repo: QueueRepoDep,
    settings: SettingsDep,
    _: PrincipalDep,
    service_date: Annotated[date | None, Query(alias="date")] = None,
    session: Annotated[SessionName, Query()] = SessionName.FULL_DAY,
) -> QueueInstanceOut:
    instance = await repo.instance_for(
        queue_id,
        service_date=service_date or settings.today(),
        session_name=session.value,
    )
    if instance is None:
        raise NotFoundError(
            f"no instance for queue {queue_id} on that date/session",
            details={"queue_id": queue_id},
        )
    return instance_out(instance)


@router.post("/{queue_id}/instance", response_model=QueueInstanceOut, status_code=201)
async def open_instance(
    queue_id: str,
    body: OpenInstanceRequest,
    service: QueueServiceDep,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.ADMIN))],
) -> QueueInstanceOut:
    require_shadow_mode_guard(settings, "open queue instance")
    instance = await service.open_instance(
        queue_id,
        service_date=body.service_date or settings.today(),
        session=body.session,
        practitioner_id=body.practitioner_id,
        service_point=body.service_point,
    )
    return instance_out(instance)


@router.post("/{queue_id}/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def issue_ticket(
    queue_id: str,
    body: IssueTicketRequest,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.ADMIN))],
) -> TicketOut:
    """Issue a token.

    Priority is classified from patient attributes by the facility's configured
    policy. `is_staff_referred_emergency` is a human at the counter saying so —
    a red flag never reaches this endpoint.
    """
    require_shadow_mode_guard(settings, "issue ticket")
    view = await service.issue(
        queue_id,
        instance_id=body.instance_id,
        attributes=PatientAttributes(
            age_years=body.age_years,
            is_pregnant=body.is_pregnant,
            is_differently_abled=body.is_differently_abled,
            has_appointment=body.has_appointment,
            is_staff_referred_emergency=body.is_staff_referred_emergency,
        ),
        patient_id=body.patient_id,
        intake_id=body.intake_id,
        appointment_slot_time=body.appointment_slot_time,
        override_priority=body.override_priority,
    )
    return ticket_out(
        view, intake_state=await _intake_state_for(repo, str(view.ticket.ticket_id))
    )


@router.get("/{queue_id}/dashboard", response_model=DashboardOut)
async def queue_dashboard(
    queue_id: str,
    repo: QueueRepoDep,
    service: QueueServiceDep,
    settings: SettingsDep,
    _: PrincipalDep,
    service_date: Annotated[date | None, Query(alias="date")] = None,
    session: Annotated[SessionName, Query()] = SessionName.FULL_DAY,
) -> DashboardOut:
    instance = await repo.instance_for(
        queue_id, service_date=service_date or settings.today(), session_name=session.value
    )
    if instance is None:
        raise NotFoundError(f"no instance for queue {queue_id}")
    return DashboardOut.model_validate(await service.dashboard(str(instance.instance_id)))


@instances_router.post("/{instance_id}/call-next", response_model=TicketOut | None)
async def call_next(
    instance_id: str,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.PHYSICIAN, Role.ADMIN))],
    practitioner_id: Annotated[str | None, Query()] = None,
    service_point: Annotated[str | None, Query()] = None,
) -> TicketOut | None:
    """Call the next patient.

    Candidate rows are locked SKIP LOCKED for the transaction, so two
    practitioners calling simultaneously on a pooled queue get different tokens.
    """
    require_shadow_mode_guard(settings, "call next")
    view = await service.call_next(
        instance_id, practitioner_id=practitioner_id, service_point=service_point
    )
    if view is None:
        return None
    return ticket_out(
        view, intake_state=await _intake_state_for(repo, str(view.ticket.ticket_id))
    )


@instances_router.post("/{instance_id}/pause", response_model=QueueInstanceOut)
async def pause_instance(
    instance_id: str,
    body: PauseRequest,
    service: QueueServiceDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.ADMIN))],
) -> QueueInstanceOut:
    return instance_out(await service.pause(instance_id, reason=body.reason))


@instances_router.post("/{instance_id}/resume", response_model=QueueInstanceOut)
async def resume_instance(
    instance_id: str,
    service: QueueServiceDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.ADMIN))],
) -> QueueInstanceOut:
    return instance_out(await service.resume(instance_id))


@instances_router.post("/{instance_id}/close", response_model=QueueInstanceOut)
async def close_instance(
    instance_id: str,
    service: QueueServiceDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.ADMIN))],
) -> QueueInstanceOut:
    """Close the session. Unserved tickets are disposed of by configured policy —
    carried forward, cancelled or reassigned — never silently dropped."""
    return instance_out(await service.close_instance(instance_id))


@instances_router.get("/{instance_id}/dashboard", response_model=DashboardOut)
async def instance_dashboard(
    instance_id: str, service: QueueServiceDep, _: PrincipalDep
) -> DashboardOut:
    return DashboardOut.model_validate(await service.dashboard(instance_id))


@tickets_router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: str, service: QueueServiceDep, repo: QueueRepoDep, _: PrincipalDep
) -> TicketOut:
    """Patient-facing ticket view, including the estimated wait.

    The wait estimate is the reason a patient uses the kiosk at all: "about 22
    minutes, enough time to record your history" is what drives adoption.
    """
    view = await service.ticket_view(ticket_id)
    return ticket_out(view, intake_state=await _intake_state_for(repo, ticket_id))


@tickets_router.post("/{ticket_id}/call", response_model=TicketOut)
async def call_ticket(
    ticket_id: str,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.PHYSICIAN, Role.ADMIN))],
) -> TicketOut:
    """Call the next patient on the instance this ticket belongs to.

    Deliberately not "call this exact ticket": jumping a specific patient ahead
    of the order is an escalation, and escalation requires an acknowledged alert.
    """
    ticket = await repo.require_ticket(ticket_id)
    view = await service.call_next(str(ticket.instance_id))
    if view is None:
        raise NotFoundError("nothing callable on that instance")
    return ticket_out(view, intake_state=await _intake_state_for(repo, str(view.ticket.ticket_id)))


@tickets_router.post("/{ticket_id}/recall", response_model=TicketOut)
async def recall_ticket(
    ticket_id: str,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.PHYSICIAN, Role.ADMIN))],
) -> TicketOut:
    """Re-insert a called-but-absent patient, or mark NO_SHOW once recalls run out."""
    view = await service.recall(ticket_id)
    return ticket_out(view, intake_state=await _intake_state_for(repo, ticket_id))


@tickets_router.post("/{ticket_id}/start", response_model=TicketOut)
async def start_ticket(
    ticket_id: str,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[Principal, Depends(require_roles(Role.PHYSICIAN, Role.STAFF, Role.ADMIN))],
) -> TicketOut:
    view = await service.start_consultation(ticket_id)
    return ticket_out(view, intake_state=await _intake_state_for(repo, ticket_id))


@tickets_router.post("/{ticket_id}/complete", response_model=TicketOut)
async def complete_ticket(
    ticket_id: str,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[Principal, Depends(require_roles(Role.PHYSICIAN, Role.STAFF, Role.ADMIN))],
) -> TicketOut:
    view = await service.complete(ticket_id)
    return ticket_out(view, intake_state=await _intake_state_for(repo, ticket_id))


@tickets_router.post("/{ticket_id}/defer", response_model=TicketOut)
async def defer_ticket(
    ticket_id: str,
    body: DeferRequest,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.PHYSICIAN, Role.ADMIN))],
) -> TicketOut:
    """Defer for a test or a payment. Priority and accrued wait are preserved."""
    view = await service.defer(ticket_id, reason=body.reason)
    return ticket_out(view, intake_state=await _intake_state_for(repo, ticket_id))


@tickets_router.post("/{ticket_id}/no-show", response_model=TicketOut)
async def no_show_ticket(
    ticket_id: str,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.ADMIN))],
) -> TicketOut:
    view = await service.no_show(ticket_id)
    return ticket_out(view, intake_state=await _intake_state_for(repo, ticket_id))


@tickets_router.post("/{ticket_id}/cancel", response_model=TicketOut)
async def cancel_ticket(
    ticket_id: str,
    body: CancelRequest,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.ADMIN))],
) -> TicketOut:
    view = await service.cancel(ticket_id, reason=body.reason)
    return ticket_out(view, intake_state=await _intake_state_for(repo, ticket_id))


@tickets_router.post("/{ticket_id}/transfer", response_model=TicketOut)
async def transfer_ticket(
    ticket_id: str,
    body: TransferRequest,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[Principal, Depends(require_roles(Role.STAFF, Role.PHYSICIAN, Role.ADMIN))],
) -> TicketOut:
    """Move a patient to another queue. The intake goes with them and is not re-run."""
    view = await service.transfer(
        ticket_id,
        target_queue_id=body.target_queue_id,
        target_instance_id=body.target_instance_id,
    )
    return ticket_out(
        view, intake_state=await _intake_state_for(repo, str(view.ticket.ticket_id))
    )


@tickets_router.post("/{ticket_id}/escalate", response_model=TicketOut)
async def escalate_ticket(
    ticket_id: str,
    body: EscalateRequest,
    service: QueueServiceDep,
    repo: QueueRepoDep,
    principal: Annotated[
        Principal, Depends(require_roles(Role.TRIAGE, Role.PHYSICIAN, Role.ADMIN))
    ],
) -> TicketOut:
    """Escalate on the strength of an acknowledged red flag.

    Rejected with 403 if the alert has not been acknowledged by a human. This is
    the mechanical guarantee behind "a red flag never auto-escalates a patient".
    """
    view = await service.escalate(
        ticket_id,
        alert_id=body.alert_id,
        acting_user_id=body.acting_user_id,
        reason=body.reason,
    )
    return ticket_out(view, intake_state=await _intake_state_for(repo, ticket_id))
