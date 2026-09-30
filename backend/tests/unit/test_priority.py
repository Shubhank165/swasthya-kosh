"""Priority classing, and the bounds that make reordering a waiting room defensible.

Decision 77 reversed a rule this system had argued for at length. These tests
are the argument for the reversal: they pin what the new ordering may do, and
more importantly what it may not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.clinical.enums import RedFlagSeverity
from app.domain.queue.priority import PRIORITY_RANK, PriorityClass, priority_for
from app.domain.record import IntakeStatus
from app.domain.worklist import WorklistEntry, WorklistState, order

NOW = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)


def entry(
    intake_id: str,
    *,
    minutes: int = 0,
    priority: PriorityClass = PriorityClass.WALKIN,
) -> WorklistEntry:
    return WorklistEntry(
        intake_id=intake_id,
        hospital_id="h1",
        state=WorklistState.READY,
        intake_status=IntakeStatus.COMPLETE,
        priority=priority,
        arrived_at=NOW + timedelta(minutes=minutes),
    )


class TestWhatMovesAnIntakeUp:
    def test_a_critical_flag_is_the_fast_lane(self) -> None:
        assert (
            priority_for(
                status=IntakeStatus.COMPLETE,
                unacknowledged_severities=[RedFlagSeverity.CRITICAL],
            )
            is PriorityClass.EMERGENCY
        )

    def test_a_high_flag_waits_its_turn(self) -> None:
        """The change decision 79 records, and the one worth stating twice.

        A `high` criterion still fires, still raises an alert, still marks the
        intake and still has to be acknowledged by a clinician. What it stops
        doing is moving the patient in front of people who arrived first.
        """

        assert (
            priority_for(
                status=IntakeStatus.COMPLETE,
                unacknowledged_severities=[RedFlagSeverity.HIGH],
            )
            is PriorityClass.WALKIN
        )

    def test_one_critical_among_several_is_enough(self) -> None:
        assert (
            priority_for(
                status=IntakeStatus.COMPLETE,
                unacknowledged_severities=[
                    RedFlagSeverity.HIGH,
                    RedFlagSeverity.HIGH,
                    RedFlagSeverity.CRITICAL,
                ],
            )
            is PriorityClass.EMERGENCY
        )

    def test_many_high_flags_never_add_up_to_a_critical_one(self) -> None:
        """Severity is not a quantity. Five moderate findings are not an
        emergency, and a rule that let them accumulate into one would be this
        module doing triage by arithmetic."""

        assert (
            priority_for(
                status=IntakeStatus.COMPLETE,
                unacknowledged_severities=[RedFlagSeverity.HIGH] * 5,
            )
            is PriorityClass.WALKIN
        )

    def test_an_interview_cut_short_is_the_same_finding(self) -> None:
        """The Jetson stops an interview only for a criterion it judged serious
        enough to stop for, and the status carries no severity of its own."""

        assert (
            priority_for(
                status=IntakeStatus.ABORTED_RED_FLAG, unacknowledged_severities=[]
            )
            is PriorityClass.EMERGENCY
        )

    @pytest.mark.parametrize(
        "status",
        [IntakeStatus.COMPLETE, IntakeStatus.PARTIAL, IntakeStatus.ABANDONED],
    )
    def test_everything_else_waits_its_turn(self, status: IntakeStatus) -> None:
        assert (
            priority_for(status=status, unacknowledged_severities=[])
            is PriorityClass.WALKIN
        )

    def test_an_acknowledged_alert_no_longer_jumps(self) -> None:
        """Acknowledgement is a person deciding. Once they have, the queue
        stops deciding for them — the service stops passing the severity."""

        assert (
            priority_for(status=IntakeStatus.COMPLETE, unacknowledged_severities=[])
            is PriorityClass.WALKIN
        )


class TestAnUnknownSeverity:
    """A device sending a value this build has never seen.

    It must not be able to reorder a waiting room by sending garbage, so the
    failure direction is *not jumping*. The alert still fires either way;
    only the overtaking is withheld.
    """

    @pytest.mark.parametrize("raw", ["catastrophic", "", "CRITICAL!", None, 7, "moderate"])
    def test_it_lands_on_the_tier_that_does_not_jump(self, raw: object) -> None:
        assert RedFlagSeverity.parse(raw) is RedFlagSeverity.HIGH

    def test_case_and_whitespace_are_not_a_new_severity(self) -> None:
        """`"  Critical "` is a critical flag with sloppy formatting, not an
        unknown value — failing that to HIGH would drop a real emergency."""

        for raw in ("CRITICAL", " critical ", "Critical"):
            assert RedFlagSeverity.parse(raw) is RedFlagSeverity.CRITICAL

    def test_an_unknown_severity_does_not_move_the_patient(self) -> None:
        assert (
            priority_for(
                status=IntakeStatus.COMPLETE,
                unacknowledged_severities=[RedFlagSeverity.parse("catastrophic")],
            )
            is PriorityClass.WALKIN
        )


class TestWhatItMayNotDo:
    def test_nothing_is_demoted_below_walkin(self) -> None:
        """WALKIN is the floor and everyone starts there.

        A scoring change can move a patient up. If one could move a patient
        down, a later rule could quietly push somebody behind people who
        arrived after them, which is the failure this bound exists to prevent.
        """

        worst = min(
            (
                priority_for(
                    status=status, unacknowledged_severities=severities, seen_at=seen
                )
                for status in IntakeStatus
                for severities in (
                    [],
                    [RedFlagSeverity.HIGH],
                    [RedFlagSeverity.CRITICAL],
                    [RedFlagSeverity.HIGH, RedFlagSeverity.CRITICAL],
                )
                for seen in (None, NOW)
            ),
            key=lambda p: -PRIORITY_RANK[p],
        )
        assert PRIORITY_RANK[worst] == PRIORITY_RANK[PriorityClass.WALKIN]

    def test_a_seen_intake_leaves_the_front(self) -> None:
        """Not because the patient matters less — because they are no longer
        waiting, and a flagged case the doctor has read would otherwise hold
        the top of the list for ever."""

        assert (
            priority_for(
                status=IntakeStatus.ABORTED_RED_FLAG,
                unacknowledged_severities=[RedFlagSeverity.CRITICAL],
                seen_at=NOW,
            )
            is PriorityClass.WALKIN
        )

    def test_the_classes_a_hospital_owns_are_never_guessed(self) -> None:
        """PRIORITY and APPOINTMENT are ranked and declared, and nothing in an
        intake record establishes either. Returning one would be this module
        inventing a status the hospital assigns."""

        produced = {
            priority_for(
                status=status, unacknowledged_severities=severities, seen_at=seen
            )
            for status in IntakeStatus
            for severities in ([], [RedFlagSeverity.HIGH], [RedFlagSeverity.CRITICAL])
            for seen in (None, NOW)
        }
        assert produced <= {PriorityClass.EMERGENCY, PriorityClass.WALKIN}


class TestOrdering:
    def test_a_flagged_arrival_overtakes_an_earlier_routine_one(self) -> None:
        routine = entry("a", minutes=0)
        flagged = entry("b", minutes=30, priority=PriorityClass.EMERGENCY)
        assert [e.intake_id for e in order([routine, flagged])] == ["b", "a"]

    def test_within_a_class_it_is_still_arrival_order(self) -> None:
        """A patient is only ever overtaken by someone the device flagged,
        never by someone who simply arrived with a better-looking record."""

        rows = [entry("c", minutes=20), entry("a", minutes=0), entry("b", minutes=10)]
        assert [e.intake_id for e in order(rows)] == ["a", "b", "c"]

    def test_two_flagged_patients_keep_their_own_arrival_order(self) -> None:
        first = entry("a", minutes=0, priority=PriorityClass.EMERGENCY)
        second = entry("b", minutes=5, priority=PriorityClass.EMERGENCY)
        assert [e.intake_id for e in order([second, first])] == ["a", "b"]

    def test_the_order_is_total_so_the_list_does_not_shuffle(self) -> None:
        """Two kiosks submitting in the same second must not swap places
        between polls."""

        same = [entry("b", minutes=0), entry("a", minutes=0)]
        assert [e.intake_id for e in order(same)] == ["a", "b"]
        assert [e.intake_id for e in order(list(reversed(same)))] == ["a", "b"]
