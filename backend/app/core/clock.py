"""Time.

The domain never reads a clock; it receives `now` as an argument. This module is
the one place a real clock exists, and the test suite substitutes `FrozenClock`
so every domain behaviour is reproducible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """UTC wall clock. Timezone-aware always — a naive datetime in a medical
    record is a bug waiting for a shift change."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Deterministic clock for tests and the evaluation harness."""

    def __init__(self, start: datetime | None = None, step: timedelta | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC)
        self._step = step or timedelta(seconds=0)

    def now(self) -> datetime:
        current = self._now
        self._now = self._now + self._step
        return current

    def advance(self, delta: timedelta) -> None:
        self._now = self._now + delta

    def set(self, value: datetime) -> None:
        self._now = value
