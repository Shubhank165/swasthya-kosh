"""What happens after the consultation: orders, stock, waiting, load.

A pilot-stage slice. `app/domain/coordination.py` states the bounds and they
apply here too — this is not inventory management and not a booking engine,
and the hospital's own systems stay the system of record for both.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.auth import RequireAdmin, RequirePhysician, RequireStaff
from app.api.deps import ClockDep, CoordinationServiceDep
from app.core.errors import ValidationError
from app.domain.coordination import OrderKind
from app.schemas.api import (
    CareOrderListOut,
    CareOrderOut,
    CareOrderRequest,
    DepartmentLoadOut,
    OperationsOut,
    StockAlertListOut,
    StockAlertOut,
    WaitEstimateOut,
)

router = APIRouter(tags=["coordination"])


@router.post(
    "/intakes/{intake_id}/orders",
    response_model=CareOrderOut,
    status_code=201,
    summary="Issue a lab, imaging, referral or prescription order",
)
async def issue_order(
    intake_id: str,
    payload: CareOrderRequest,
    principal: RequirePhysician,
    service: CoordinationServiceDep,
) -> CareOrderOut:
    """Record one order, with a slot when the destination has one free.

    A referral or scan that finds no capacity comes back `unfilled` rather than
    `requested` with a blank time. One says the hospital could not offer an
    appointment; the other says nobody has looked. A patient walking across a
    site deserves to know which.

    Issuing is a physician's act and is recorded against their id, for the same
    reason verification is: an order nobody signed is an order nobody owns.
    """

    try:
        kind = OrderKind(payload.kind)
    except ValueError as exc:
        raise ValidationError(f"unknown order kind: {payload.kind!r}") from exc

    await service.require_intake(intake_id)
    record = await service.issue(
        intake_id=intake_id,
        kind=kind,
        code=payload.code,
        display=payload.display,
        ordered_by=principal.user_id,
        destination=payload.destination,
        note=payload.note,
    )
    return CareOrderOut.model_validate(record)


@router.get(
    "/intakes/{intake_id}/orders",
    response_model=CareOrderListOut,
    summary="Everything asked for on this intake",
)
async def list_orders(
    intake_id: str,
    principal: RequireStaff,
    service: CoordinationServiceDep,
) -> CareOrderListOut:
    records = await service.orders_for(intake_id)
    return CareOrderListOut(
        intake_id=intake_id,
        orders=tuple(CareOrderOut.model_validate(row) for row in records),
    )


@router.get(
    "/pharmacy/alerts",
    response_model=StockAlertListOut,
    summary="Items low, expiring, expired or out",
)
async def stock_alerts(
    principal: RequireStaff,
    service: CoordinationServiceDep,
    clock: ClockDep,
) -> StockAlertListOut:
    """What a pharmacist should see before a patient reaches the counter.

    Items the pharmacy has never recorded are absent rather than listed as a
    shortage: "we have none" and "we have never heard of it" are different
    answers, and only one of them is an alert.
    """

    alerts = await service.stock_alerts()
    return StockAlertListOut(
        generated_at=clock.now(),
        alerts=tuple(
            StockAlertOut(
                code=item.code,
                display=item.display,
                on_hand=item.on_hand,
                reorder_level=item.reorder_level,
                expires_on=item.expires_on,
                state=state.value,
            )
            for item, state in alerts
        ),
    )


@router.get(
    "/intakes/{intake_id}/wait",
    response_model=WaitEstimateOut,
    summary="Queue position, and a time when the data supports one",
)
async def wait_estimate(
    intake_id: str,
    principal: RequireStaff,
    service: CoordinationServiceDep,
) -> WaitEstimateOut:
    """Where this patient stands.

    `minutes` is null and `confident` false when the department has not yet
    seen enough patients today to average over. A waiting room told "about
    eight minutes" that waits ninety stops believing the screen, so the
    estimate says when it does not know.
    """

    intake = await service.require_intake(intake_id)
    estimate = await service.wait_estimate(
        intake_id=intake_id, department_code=intake.department_code
    )
    return WaitEstimateOut(
        intake_id=intake_id,
        position=estimate.position,
        ahead=estimate.ahead,
        minutes=estimate.minutes,
        confident=estimate.confident,
    )


@router.get(
    "/operations",
    response_model=OperationsOut,
    summary="Waiting, flagged and unfilled, by department",
)
async def operations(
    principal: RequireAdmin,
    service: CoordinationServiceDep,
    clock: ClockDep,
) -> OperationsOut:
    """Where the time is going, longest wait first.

    Counted over the last day from rows this system already holds. Nothing is
    modelled, forecast or predicted — the number an administrator wants is how
    long the person who has been waiting longest has been waiting, and that is
    a subtraction.
    """

    loads = await service.load()
    return OperationsOut(
        generated_at=clock.now(),
        departments=tuple(DepartmentLoadOut.model_validate(load) for load in loads),
    )
