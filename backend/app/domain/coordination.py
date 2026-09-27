"""What happens to a patient after the consultation, as data.

The report ends at the door of the room. Everything a doctor does next — send
for a test, refer to another department, write a prescription — leaves the
system as paper and stops being trackable. This module is the small, honest
core of making those four acts into records that travel.

**Scope, stated plainly, because overstating it would be the failure here.**
This is a pilot-stage slice, not hospital inventory management and not a queue
system. A hospital already has both, and `worklist.py`'s original docstring
made the point this module has to respect: every line of queue code is a line
that has to agree with whatever the HMIS decides. So:

- Stock is a *count and an expiry date*, so a prescription can say "this is not
  on the shelf" at the moment it is written. It does not do goods receipt,
  batch tracking, consumption reconciliation or reorder workflow, and a
  hospital pharmacy system remains the system of record.
- Slots are *declared capacity*, so a referral can carry an appointment rather
  than a hope. They are not a booking engine and they do not own a calendar.
- The analytics are arithmetic over rows this system already holds. Nothing is
  modelled, forecast or predicted.

Everything here is pure: dataclasses and functions over values handed in. The
service layer reads and writes; this module decides. That is the same split the
report builder uses, and for the same reason — it is what keeps the decisions
testable without a database.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum


class OrderKind(StrEnum):
    """What the doctor asked for."""

    LAB = "lab"
    IMAGING = "imaging"
    REFERRAL = "referral"
    PRESCRIPTION = "prescription"


class OrderStatus(StrEnum):
    """Where it has got to.

    `REQUESTED` is the only status this system sets on its own. The rest are
    recorded when somebody tells it — a slot was booked, a sample was taken, a
    patient did not attend. A status this system invented would be a claim
    about the world it cannot check.
    """

    REQUESTED = "requested"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    #: Asked for, and the destination had no capacity to offer.
    UNFILLED = "unfilled"


@dataclass(frozen=True, slots=True)
class Slot:
    """One declared unit of capacity at a destination."""

    slot_id: str
    destination: str
    starts_at: datetime
    capacity: int
    booked: int = 0

    @property
    def free(self) -> int:
        return max(0, self.capacity - self.booked)


@dataclass(frozen=True, slots=True)
class StockItem:
    """What the pharmacy says it holds of one medicine."""

    code: str
    display: str
    on_hand: int
    reorder_level: int
    expires_on: date | None = None


class StockState(StrEnum):
    """How a prescription for this item should be read."""

    #: Enough on the shelf, and not close to expiry.
    AVAILABLE = "available"
    #: At or below the level the pharmacy asked to be warned at.
    LOW = "low"
    #: Expiry falls inside the warning window. Still on the shelf; not for long.
    EXPIRING = "expiring"
    #: Expiry has passed. This is not a warning, it is a stop.
    EXPIRED = "expired"
    #: None on the shelf.
    OUT = "out"
    #: The pharmacy does not stock it, or has never told us about it. Distinct
    #: from OUT on purpose: "we have none" and "we have never heard of it" are
    #: different answers, and collapsing them would let an unstocked item read
    #: as a temporary shortage.
    UNKNOWN = "unknown"


#: How far ahead an expiry date counts as a warning rather than a fact.
EXPIRY_WARNING = timedelta(days=30)


def stock_state(item: StockItem | None, *, today: date) -> StockState:
    """How to read the shelf for one prescribed item.

    Order matters and is strongest-first: an expired box is a stop regardless
    of how many are in it, and a shelf with none on it is out regardless of
    what the reorder level says.
    """

    if item is None:
        return StockState.UNKNOWN
    if item.expires_on is not None and item.expires_on < today:
        return StockState.EXPIRED
    if item.on_hand <= 0:
        return StockState.OUT
    if item.expires_on is not None and item.expires_on - today <= EXPIRY_WARNING:
        return StockState.EXPIRING
    if item.on_hand <= item.reorder_level:
        return StockState.LOW
    return StockState.AVAILABLE


#: States a pharmacist should be shown before the patient walks to the counter.
ACTIONABLE_STOCK: frozenset[StockState] = frozenset(
    {StockState.LOW, StockState.EXPIRING, StockState.EXPIRED, StockState.OUT}
)


def next_free_slot(slots: Sequence[Slot], *, after: datetime) -> Slot | None:
    """The earliest slot at or after `after` with room in it.

    Returns `None` rather than the closest near-miss. A referral that names a
    full slot is worse than one that admits there was nothing: the patient
    travels either way, and only one of those tells them the truth.
    """

    candidates = [s for s in slots if s.starts_at >= after and s.free > 0]
    return min(candidates, key=lambda s: (s.starts_at, s.slot_id), default=None)


@dataclass(frozen=True, slots=True)
class QueueEstimate:
    """How long a waiting patient is told to expect.

    `confident` is the whole point of the structure. An estimate built from
    fewer than a handful of completed consultations is arithmetic on noise, and
    a waiting room that is told "about 8 minutes" and waits ninety stops
    believing the screen. When it is False the caller shows a position and no
    time.
    """

    position: int
    ahead: int
    minutes: int | None
    confident: bool


#: Below this many completed consultations, the per-patient rate is noise.
MIN_OBSERVATIONS = 5


def estimate_wait(
    *,
    position: int,
    completed_minutes: Sequence[float],
) -> QueueEstimate:
    """Position in the queue, and a time only when the data supports one.

    The rate is the mean of what this department actually did today, not a
    configured constant — a constant is a promise about a clinic nobody has
    measured. With too few observations the estimate carries a position and a
    null time, and says so.
    """

    ahead = max(0, position - 1)
    if len(completed_minutes) < MIN_OBSERVATIONS:
        return QueueEstimate(
            position=position, ahead=ahead, minutes=None, confident=False
        )
    rate = sum(completed_minutes) / len(completed_minutes)
    return QueueEstimate(
        position=position,
        ahead=ahead,
        minutes=round(ahead * rate),
        confident=True,
    )


@dataclass(frozen=True, slots=True)
class DepartmentLoad:
    """One row of the operations view."""

    department_code: str
    waiting: int
    flagged: int
    longest_wait_minutes: int
    unfilled_orders: int


def department_loads(
    *,
    rows: Sequence[tuple[str | None, datetime, bool]],
    unfilled: dict[str, int],
    now: datetime,
) -> tuple[DepartmentLoad, ...]:
    """Where the time is going, counted rather than modelled.

    `rows` is (department, arrived_at, is_flagged) for everything still
    waiting. Ordered by longest wait first, because that is the number an
    administrator is looking for: not the busiest department, the one with
    somebody in it who has been there longest.
    """

    grouped: dict[str, list[tuple[datetime, bool]]] = {}
    for department, arrived_at, flagged in rows:
        grouped.setdefault(department or "unassigned", []).append((arrived_at, flagged))

    loads = [
        DepartmentLoad(
            department_code=department,
            waiting=len(entries),
            flagged=sum(1 for _, flagged in entries if flagged),
            longest_wait_minutes=int(
                max((now - arrived).total_seconds() for arrived, _ in entries) // 60
            ),
            unfilled_orders=unfilled.get(department, 0),
        )
        for department, entries in grouped.items()
    ]
    return tuple(
        sorted(loads, key=lambda load: (-load.longest_wait_minutes, load.department_code))
    )
