"""Red-flag alert repository.

`acknowledge` is the pivot of the whole safety design: it is the only place an
alert acquires an acknowledging user, and `escalate` refuses to act on an alert
that has not been through it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.domain.clinical.provenance import UserId
from app.domain.redflags.evaluator import RedFlagAlert
from app.models.clinical import RedFlagAlertRecord
from app.repositories.mappers import alert_from_row, alert_to_row


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_intake(self, intake_id: str) -> tuple[RedFlagAlert, ...]:
        result = await self._session.execute(
            select(RedFlagAlertRecord)
            .where(RedFlagAlertRecord.intake_id == intake_id)
            .order_by(RedFlagAlertRecord.raised_at)
        )
        return tuple(alert_from_row(row) for row in result.scalars().all())

    async def get(self, alert_id: str) -> RedFlagAlert | None:
        row = await self._session.get(RedFlagAlertRecord, alert_id)
        return None if row is None else alert_from_row(row)

    async def require(self, alert_id: str) -> RedFlagAlert:
        alert = await self.get(alert_id)
        if alert is None:
            raise NotFoundError(f"alert {alert_id} not found", details={"alert_id": alert_id})
        return alert

    async def raise_alerts(
        self, alerts: tuple[RedFlagAlert, ...], *, intake_id: str
    ) -> tuple[RedFlagAlert, ...]:
        """Persist newly fired alerts, skipping any already on record.

        A rule that keeps matching as the patient answers more questions must not
        produce a new alert on every answer.
        """
        existing = {a.rule_id for a in await self.list_for_intake(intake_id)}
        stored: list[RedFlagAlert] = []
        for alert in alerts:
            if alert.rule_id in existing:
                continue
            self._session.add(alert_to_row(alert, intake_id=intake_id))
            stored.append(alert)
        await self._session.flush()
        return tuple(stored)

    async def acknowledge(
        self, alert_id: str, *, user_id: UserId, now: datetime
    ) -> RedFlagAlert:
        """A human takes responsibility for the alert.

        Idempotent for the same user; a second, different acknowledger is a
        conflict rather than a silent overwrite, because the record has to say
        who actually looked.
        """
        row = await self._session.get(RedFlagAlertRecord, alert_id)
        if row is None:
            raise NotFoundError(f"alert {alert_id} not found", details={"alert_id": alert_id})
        if row.dismissed_by is not None:
            raise ConflictError(
                "a dismissed alert cannot be acknowledged", details={"alert_id": alert_id}
            )
        if row.acknowledged_by is not None and row.acknowledged_by != str(user_id):
            raise ConflictError(
                "alert was already acknowledged by another user",
                details={"alert_id": alert_id, "acknowledged_by": row.acknowledged_by},
            )
        row.acknowledged_by = str(user_id)
        row.acknowledged_at = row.acknowledged_at or now
        await self._session.flush()
        return alert_from_row(row)

    async def dismiss(
        self, alert_id: str, *, user_id: UserId, now: datetime, reason: str
    ) -> RedFlagAlert:
        row = await self._session.get(RedFlagAlertRecord, alert_id)
        if row is None:
            raise NotFoundError(f"alert {alert_id} not found", details={"alert_id": alert_id})
        if row.acknowledged_by is not None:
            raise ConflictError(
                "an acknowledged alert cannot be dismissed", details={"alert_id": alert_id}
            )
        if not reason:
            raise ConflictError("dismissing an alert requires a reason")
        row.dismissed_by = str(user_id)
        row.dismissed_at = now
        row.dismissal_reason = reason
        await self._session.flush()
        return alert_from_row(row)
