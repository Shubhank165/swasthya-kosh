"""Event bus.

One protocol, two implementations. `InProcessBus` is what tests and a single-node
on-prem deployment run; `PubSubBus` is the cloud shape and is where NATS would
slot in for a hospital that wants a broker. Nothing above this module knows
which is in use.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol

from app.core.logging import get_logger
from app.events.schemas import Event, EventName

logger = get_logger(__name__)

Handler = Callable[[Event], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, event: Event) -> None: ...

    async def publish_all(self, events: Sequence[Event]) -> None: ...

    def subscribe(self, handler: Handler, *, names: Sequence[EventName] | None = None) -> None: ...


class InProcessBus:
    """Synchronous fan-out within one process.

    Handler failures are logged and swallowed: a dashboard socket that has gone
    away must never roll back a clinical write.
    """

    def __init__(self) -> None:
        self._handlers: list[tuple[Handler, frozenset[EventName] | None]] = []
        self._published: list[Event] = []
        self._record_history = False

    def subscribe(
        self, handler: Handler, *, names: Sequence[EventName] | None = None
    ) -> None:
        self._handlers.append((handler, frozenset(names) if names else None))

    async def publish(self, event: Event) -> None:
        if self._record_history:
            self._published.append(event)
        for handler, names in list(self._handlers):
            if names is not None and event.name not in names:
                continue
            try:
                await handler(event)
            except Exception:  # a subscriber must never break a clinical write
                logger.warning(
                    "event_handler_failed", event=event.name.value, intake_id=event.intake_id
                )

    async def publish_all(self, events: Sequence[Event]) -> None:
        for event in events:
            await self.publish(event)

    # --- test support -------------------------------------------------------

    def record_history(self, enabled: bool = True) -> None:
        """Keep published events for assertion. Off in production."""
        self._record_history = enabled

    @property
    def history(self) -> tuple[Event, ...]:
        return tuple(self._published)

    def clear(self) -> None:
        self._published.clear()


class PubSubBus:
    """Cloud fan-out.

    Deliberately unimplemented in this build: the protocol and the wiring exist
    so the swap is a config change, but there is no cloud dependency to break in
    CI and nothing here pretends to work.
    """

    def __init__(self, topic: str) -> None:
        self._topic = topic
        self._local = InProcessBus()

    def subscribe(
        self, handler: Handler, *, names: Sequence[EventName] | None = None
    ) -> None:
        self._local.subscribe(handler, names=names)

    async def publish(self, event: Event) -> None:
        raise NotImplementedError(
            "PubSubBus is a placeholder for the cloud profile; this build runs InProcessBus"
        )

    async def publish_all(self, events: Sequence[Event]) -> None:
        raise NotImplementedError(
            "PubSubBus is a placeholder for the cloud profile; this build runs InProcessBus"
        )


_bus: InProcessBus | None = None
_lock = asyncio.Lock()


async def get_event_bus() -> InProcessBus:
    """Process-wide bus. FastAPI dependency."""
    global _bus
    if _bus is None:
        async with _lock:
            if _bus is None:
                _bus = InProcessBus()
    return _bus


def reset_event_bus() -> None:
    """Drop the process-wide bus. Used between tests."""
    global _bus
    _bus = None
