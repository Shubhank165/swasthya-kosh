"""The care-coordination decisions, tested without a database.

These are the four acts that used to leave the system as paper. The tests
worth having are the ones that pin what the module refuses to claim.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.coordination import (
    ACTIONABLE_STOCK,
    MIN_OBSERVATIONS,
    DepartmentLoad,
    Slot,
    StockItem,
    StockState,
    department_loads,
    estimate_wait,
    next_free_slot,
    stock_state,
)

TODAY = date(2026, 9, 28)
NOW = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)


def item(**kwargs: object) -> StockItem:
    base = {
        "code": "metformin_500",
        "display": "Metformin 500 mg",
        "on_hand": 50,
        "reorder_level": 10,
    }
    return StockItem(**{**base, **kwargs})  # type: ignore[arg-type]


class TestReadingTheShelf:
    def test_plenty_on_hand_and_far_from_expiry(self) -> None:
        assert stock_state(item(), today=TODAY) is StockState.AVAILABLE

    def test_at_the_reorder_level_is_already_low(self) -> None:
        """At, not below. A pharmacist who asked to be warned at ten wants the
        warning when it reaches ten."""

        assert stock_state(item(on_hand=10), today=TODAY) is StockState.LOW

    def test_nothing_on_the_shelf_is_out(self) -> None:
        assert stock_state(item(on_hand=0), today=TODAY) is StockState.OUT

    def test_expiry_inside_the_window_warns(self) -> None:
        soon = TODAY + timedelta(days=10)
        assert stock_state(item(expires_on=soon), today=TODAY) is StockState.EXPIRING

    def test_an_expired_box_is_a_stop_however_many_are_in_it(self) -> None:
        """Strongest-first ordering: quantity does not rescue an expired item."""

        gone = TODAY - timedelta(days=1)
        assert stock_state(item(on_hand=900, expires_on=gone), today=TODAY) is StockState.EXPIRED

    def test_an_empty_shelf_beats_the_reorder_level(self) -> None:
        assert stock_state(item(on_hand=0, reorder_level=50), today=TODAY) is StockState.OUT

    def test_never_stocked_is_not_the_same_as_none_left(self) -> None:
        """"We have none" and "we have never heard of it" are different answers
        to a doctor writing a prescription, and collapsing them would let an
        unstocked item read as a temporary shortage."""

        assert stock_state(None, today=TODAY) is StockState.UNKNOWN
        assert StockState.UNKNOWN not in ACTIONABLE_STOCK

    @pytest.mark.parametrize(
        "state", [StockState.LOW, StockState.EXPIRING, StockState.EXPIRED, StockState.OUT]
    )
    def test_every_bad_state_reaches_the_pharmacist(self, state: StockState) -> None:
        assert state in ACTIONABLE_STOCK

    def test_available_is_not_something_to_act_on(self) -> None:
        assert StockState.AVAILABLE not in ACTIONABLE_STOCK


class TestFindingASlot:
    def slots(self) -> list[Slot]:
        return [
            Slot("s1", "radiology", NOW - timedelta(hours=1), capacity=2),
            Slot("s2", "radiology", NOW + timedelta(hours=1), capacity=1, booked=1),
            Slot("s3", "radiology", NOW + timedelta(hours=2), capacity=1),
            Slot("s4", "radiology", NOW + timedelta(hours=3), capacity=5),
        ]

    def test_it_takes_the_earliest_with_room(self) -> None:
        found = next_free_slot(self.slots(), after=NOW)
        assert found is not None and found.slot_id == "s3"

    def test_a_full_slot_is_skipped_not_offered(self) -> None:
        found = next_free_slot(self.slots(), after=NOW)
        assert found is not None and found.slot_id != "s2"

    def test_the_past_is_not_offered(self) -> None:
        found = next_free_slot(self.slots(), after=NOW)
        assert found is not None and found.slot_id != "s1"

    def test_nothing_free_returns_nothing_rather_than_a_near_miss(self) -> None:
        """A referral naming a full slot is worse than one admitting there was
        none: the patient travels either way, and only one tells the truth."""

        full = [Slot("x", "radiology", NOW + timedelta(hours=1), capacity=1, booked=1)]
        assert next_free_slot(full, after=NOW) is None

    def test_overbooked_capacity_never_reads_as_free(self) -> None:
        over = Slot("x", "radiology", NOW, capacity=1, booked=4)
        assert over.free == 0


class TestTellingAPatientHowLong:
    def test_too_little_data_gives_a_position_and_no_time(self) -> None:
        """A waiting room told 'about 8 minutes' that waits ninety stops
        believing the screen."""

        estimate = estimate_wait(position=4, completed_minutes=[6.0, 7.0])
        assert estimate.position == 4
        assert estimate.ahead == 3
        assert estimate.minutes is None
        assert estimate.confident is False

    def test_enough_data_gives_a_time(self) -> None:
        estimate = estimate_wait(
            position=4, completed_minutes=[6.0] * MIN_OBSERVATIONS
        )
        assert estimate.confident is True
        assert estimate.minutes == 18  # three ahead at six minutes each

    def test_the_patient_at_the_front_waits_for_nobody(self) -> None:
        estimate = estimate_wait(position=1, completed_minutes=[6.0] * MIN_OBSERVATIONS)
        assert estimate.ahead == 0
        assert estimate.minutes == 0

    def test_the_rate_is_measured_not_assumed(self) -> None:
        """Two departments with the same queue length and different throughput
        must not be given the same number."""

        fast = estimate_wait(position=3, completed_minutes=[4.0] * MIN_OBSERVATIONS)
        slow = estimate_wait(position=3, completed_minutes=[20.0] * MIN_OBSERVATIONS)
        assert fast.minutes == 8
        assert slow.minutes == 40


class TestWhereTheTimeIsGoing:
    def rows(self) -> list[tuple[str | None, datetime, bool]]:
        return [
            ("general", NOW - timedelta(minutes=10), False),
            ("general", NOW - timedelta(minutes=90), False),
            ("ortho", NOW - timedelta(minutes=30), True),
            (None, NOW - timedelta(minutes=5), False),
        ]

    def test_longest_wait_sorts_first(self) -> None:
        """Not the busiest department — the one with somebody in it who has
        been there longest. That is the number an administrator looks for."""

        loads = department_loads(rows=self.rows(), unfilled={}, now=NOW)
        assert [load.department_code for load in loads] == ["general", "ortho", "unassigned"]
        assert loads[0].longest_wait_minutes == 90

    def test_it_counts_rather_than_models(self) -> None:
        loads = department_loads(rows=self.rows(), unfilled={"ortho": 2}, now=NOW)
        by_code = {load.department_code: load for load in loads}
        assert by_code["general"] == DepartmentLoad(
            department_code="general",
            waiting=2,
            flagged=0,
            longest_wait_minutes=90,
            unfilled_orders=0,
        )
        assert by_code["ortho"].flagged == 1
        assert by_code["ortho"].unfilled_orders == 2

    def test_an_unassigned_department_is_shown_not_dropped(self) -> None:
        """An intake with no department is exactly the kind of thing an
        operations view exists to surface."""

        loads = department_loads(rows=self.rows(), unfilled={}, now=NOW)
        assert any(load.department_code == "unassigned" for load in loads)

    def test_nothing_waiting_is_an_empty_view_not_a_crash(self) -> None:
        assert department_loads(rows=[], unfilled={}, now=NOW) == ()
