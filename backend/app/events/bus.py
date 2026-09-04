"""Event bus.

One protocol, one implementation: synchronous fan-out within a process, which
is what drives the dashboard sockets and the demo timeline.

There used to be a `PubSubBus` here that raised `NotImplementedError` from every
method, and an `EVENT_BUS` setting that selected it. Both are gone. Cross-
instance fan-out needs a broker-backed bus that nothing in this build
implements, and a config switch that appears to offer it is worse than not
offering it — somebody sets `EVENT_BUS=pubsub`, sees no error at startup, and
believes a second API instance is receiving events.

What genuinely does span instances is the OCR work queue, which is a different
problem with a real implementation: see `app.adapters.queue.dispatch`.
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
