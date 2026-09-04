"""WebSocket fan-out hub.

Two channels: `/ws/dashboard` for staff, filtered by department, and
`/ws/intakes/{id}` for the kiosk driving one session.

Every frame is built from an `Event`, and events carry identifiers and counters
only — never clinical text. A waiting-room screen showing "KC-014" must never be
one bug away from showing why that patient is here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger
from app.events.schemas import Event, EventName

logger = get_logger(__name__)

#: Events a worklist subscriber receives. Everything that changes what a doctor
#: or a triage nurse would do next, and nothing that does not.
WORKLIST_EVENTS: frozenset[EventName] = frozenset(
    {
        EventName.INTAKE_RECEIVED,
        EventName.INTAKE_NEEDS_REVIEW,
        EventName.INTAKE_SEEN,
        EventName.REDFLAG_RECEIVED,
        EventName.REDFLAG_ACKNOWLEDGED,
        EventName.CONTRADICTION_DETECTED,
        EventName.DOCUMENT_PROCESSED,
        EventName.DOCUMENT_LOW_CONFIDENCE,
        EventName.DOCUMENT_REJECTED,
        EventName.REPORT_READY,
        EventName.REPORT_PHYSICIAN_VERIFIED,
    }
)

#: Kept under its old name so an existing dashboard client does not break.
DASHBOARD_EVENTS = WORKLIST_EVENTS

#: Events the kiosk that submitted one intake receives — chiefly so it can show
#: "your prescription has been read" while the patient is still standing there.
INTAKE_EVENTS: frozenset[EventName] = frozenset(
    {
        EventName.INTAKE_RECEIVED,
        EventName.INTAKE_UPDATED,
        EventName.DOCUMENT_UPLOADED,
        EventName.DOCUMENT_PROCESSED,
        EventName.DOCUMENT_LOW_CONFIDENCE,
        EventName.DOCUMENT_REJECTED,
    }
)


@dataclass
class Subscription:
    """One connected socket and what it wants."""

    socket: WebSocket
    names: frozenset[EventName]
    department_code: str | None = None
    intake_id: str | None = None

    def wants(self, event: Event) -> bool:
        if event.name not in self.names:
            return False
        if self.intake_id is not None:
            return event.intake_id == self.intake_id
        if self.department_code is not None:
            # Ticket events carry a department; intake and alert events may not,
            # and a staff dashboard should still see those.
            return event.department_code in (None, self.department_code)
        return True


class RealtimeHub:
    """Tracks sockets and pushes events to the ones that want them."""

    def __init__(self) -> None:
        self._subscriptions: list[Subscription] = []
        self._lock = asyncio.Lock()

    async def connect(
        self,
        socket: WebSocket,
        *,
        names: Iterable[EventName],
        department_code: str | None = None,
        intake_id: str | None = None,
    ) -> Subscription:
        await socket.accept()
        subscription = Subscription(
            socket=socket,
            names=frozenset(names),
            department_code=department_code,
            intake_id=intake_id,
        )
        async with self._lock:
            self._subscriptions.append(subscription)
        return subscription

    async def disconnect(self, subscription: Subscription) -> None:
        async with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)

    async def broadcast(self, event: Event) -> None:
        """Push `event` to every interested socket.

        A dead socket is dropped rather than retried: the clinical write that
        produced this event has already committed, and a disconnected display
        must not be able to affect it.
        """
        frame = event.to_dict()
        async with self._lock:
            targets = [s for s in self._subscriptions if s.wants(event)]
        dead: list[Subscription] = []
        for subscription in targets:
            try:
                await subscription.socket.send_json(frame)
            except Exception:  # a disconnected display must not break anything
                dead.append(subscription)
        for subscription in dead:
            await self.disconnect(subscription)
        if dead:
            logger.info("realtime_dropped_sockets", count=len(dead))

    async def send(self, subscription: Subscription, payload: dict[str, Any]) -> None:
        await subscription.socket.send_json(payload)

    @property
    def connection_count(self) -> int:
        return len(self._subscriptions)


_hub: RealtimeHub | None = None


def get_hub() -> RealtimeHub:
    global _hub
    if _hub is None:
        _hub = RealtimeHub()
    return _hub


def reset_hub() -> None:
    global _hub
    _hub = None
