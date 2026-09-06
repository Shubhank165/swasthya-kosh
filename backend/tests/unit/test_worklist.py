"""The worklist — §8.4.

Two claims, and the second one is the reason this file exists:

1. Ordering is **arrival time**, and nothing else moves a row.
2. A fired red-flag criterion raises an alert a person acknowledges. It does
   **not** move the intake up the list.

Software that reorders a waiting room on its own reading of a symptom has made a
triage decision. This system is not permitted to make one, and the way that
stays true is a test that fails the moment somebody adds a sort key.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.record import IntakeStatus
from app.domain.worklist import (
    Worklist,
    WorklistEntry,
    WorklistState,
    assemble,
    order,
    state_for,
)

BASE = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


def _entry(
    intake_id: str = "i1",
    *,
    minutes: int = 0,
    state: WorklistState = WorklistState.READY,
    status: IntakeStatus = IntakeStatus.COMPLETE,
    alerts: int = 0,
) -> WorklistEntry:
    return WorklistEntry(
        intake_id=intake_id,
        hospital_id="aiia-delhi",
        department_code="kayachikitsa",
        state=state,
        intake_status=status,
        arrived_at=BASE + timedelta(minutes=minutes),
        unacknowledged_alerts=alerts,
    )


class TestWhatStateARowShows:
    def test_a_finished_intake_with_nothing_outstanding_is_ready(self) -> None:
        assert (
            state_for(
                status=IntakeStatus.COMPLETE,
                unacknowledged_alerts=0,
                seen_at=None,
                needs_review=False,
            )
            is WorklistState.READY
        )

    @pytest.mark.parametrize(
        "status", [IntakeStatus.PARTIAL, IntakeStatus.ABANDONED]
    )
    def test_an_unfinished_interview_is_partial_rather_than_hidden(
        self, status: IntakeStatus
    ) -> None:
        """A partial history is still a history.

        It appears on the list with the rest marked unanswered. Hiding it would
        lose every answer the patient did give.
        """
        assert (
            state_for(
                status=status,
                unacknowledged_alerts=0,
                seen_at=None,
                needs_review=False,
            )
            is WorklistState.PARTIAL
        )

    def test_an_unacknowledged_alert_outranks_an_unfinished_interview(self) -> None:
        assert (
            state_for(
                status=IntakeStatus.PARTIAL,
                unacknowledged_alerts=1,
                seen_at=None,
                needs_review=True,
            )
            is WorklistState.RED_FLAG_PENDING
        )

    def test_something_needing_a_human_outranks_partial(self) -> None:
        assert (
            state_for(
                status=IntakeStatus.PARTIAL,
                unacknowledged_alerts=0,
                seen_at=None,
                needs_review=True,
            )
            is WorklistState.NEEDS_REVIEW
        )

    def test_a_doctor_having_seen_it_outranks_everything(self) -> None:
        """Strongest precedence, deliberately.

        Once a physician has the record open, the dashboard's job is done; a row
        that kept flashing an alert a doctor is already reading is noise, and
        noise is what makes the next alert ignorable.
        """
        assert (
            state_for(
                status=IntakeStatus.PARTIAL,
                unacknowledged_alerts=3,
                seen_at=BASE,
                needs_review=True,
            )
            is WorklistState.SEEN
        )

    @pytest.mark.parametrize(
        ("state", "actionable"),
        [
            (WorklistState.READY, False),
            (WorklistState.PARTIAL, False),
            (WorklistState.SEEN, False),
            (WorklistState.RED_FLAG_PENDING, True),
            (WorklistState.NEEDS_REVIEW, True),
        ],
    )
    def test_actionable_means_a_person_has_something_to_do(
        self, state: WorklistState, actionable: bool
    ) -> None:
        assert _entry(state=state).is_actionable is actionable


class TestOrdering:
    def test_it_is_arrival_order_oldest_first(self) -> None:
        rows = [_entry("late", minutes=30), _entry("early", minutes=5)]
        assert [entry.intake_id for entry in order(rows)] == ["early", "late"]

    def test_a_red_flag_does_not_move_a_row_up_the_list(self) -> None:
        """The claim the module exists to keep true.

        The alert is surfaced separately so nobody can scroll past it. The
        *position* stays arrival order, because reordering a waiting room on a
        machine's reading of a symptom is a triage decision.
        """
        rows = [
            _entry("early", minutes=0),
            _entry(
                "flagged",
                minutes=45,
                state=WorklistState.RED_FLAG_PENDING,
                status=IntakeStatus.ABORTED_RED_FLAG,
                alerts=1,
            ),
        ]
        assert [entry.intake_id for entry in order(rows)] == ["early", "flagged"]

    def test_a_tie_is_broken_so_the_list_does_not_shuffle_between_polls(
        self,
    ) -> None:
        """Two kiosks submitting in the same second must not reorder a
        dashboard that repolls every few seconds."""
        rows = [_entry("b", minutes=10), _entry("a", minutes=10)]
        assert [entry.intake_id for entry in order(rows)] == ["a", "b"]
        assert order(rows) == order(list(reversed(rows)))

    def test_ordering_an_empty_list_is_an_empty_list(self) -> None:
        assert order([]) == ()


class TestAssembly:
    def test_the_alerts_are_pulled_out_so_they_cannot_be_scrolled_past(
        self,
    ) -> None:
        rows = [
            _entry("early", minutes=0),
            _entry("flagged", minutes=45, state=WorklistState.RED_FLAG_PENDING, alerts=1),
            _entry("later", minutes=60),
        ]
        worklist = assemble(rows, department_code="kayachikitsa", generated_at=BASE)
        assert [entry.intake_id for entry in worklist.pending_alerts] == ["flagged"]
        assert worklist.total == 3
        assert worklist.department_code == "kayachikitsa"

    def test_an_acknowledged_alert_leaves_the_pending_list(self) -> None:
        """Acknowledgement is a record of a person having looked, and that is
        all it does — but the row does stop demanding attention."""
        rows = [_entry("seen", minutes=5, state=WorklistState.SEEN, alerts=0)]
        assert assemble(rows).pending_alerts == ()

    def test_the_entries_are_ordered_by_arrival_not_by_state(self) -> None:
        rows = [
            _entry("flagged", minutes=90, state=WorklistState.RED_FLAG_PENDING, alerts=1),
            _entry("ready", minutes=1),
        ]
        assert [entry.intake_id for entry in assemble(rows).entries] == [
            "ready",
            "flagged",
        ]

    def test_an_empty_worklist_is_valid(self) -> None:
        empty = assemble([])
        assert empty.entries == ()
        assert empty.pending_alerts == ()
        assert empty.total == 0


class TestTheRowCarriesNoClinicalText:
    """This structure reaches a waiting-room-adjacent dashboard and the
    WebSocket feed behind it. Neither is a place a patient's history may
    appear."""

    def test_an_entry_holds_identifiers_enums_and_counters_only(self) -> None:
        allowed = {
            "intake_id",
            "hospital_id",
            "department_code",
            "state",
            "intake_status",
            "arrived_at",
            "language",
            "unacknowledged_alerts",
            "unresolved_count",
            "contradiction_count",
            "needs_verification",
            "repaired",
            # A boolean. Says the repair path could not rescue the payload, not
            # what was in it — 3/3 §4.1.
            "needs_manual_review",
            "patient_ref_type",
            "seen_at",
        }
        assert set(WorklistEntry.model_fields) == allowed

    def test_it_counts_unresolved_fields_rather_than_naming_them(self) -> None:
        """A field *name* on a public screen is a clinical disclosure —
        "pregnancy: unresolved" beside a queue number tells the room something
        about that patient."""
        annotation = WorklistEntry.model_fields["unresolved_count"].annotation
        assert annotation is int

    def test_a_row_refuses_a_field_nobody_declared(self) -> None:
        """`extra="forbid"`, so a well-meaning addition of `chief_complaint`
        fails here rather than appearing on a screen."""
        with pytest.raises(ValueError, match="chief_complaint"):
            WorklistEntry(
                intake_id="i1",
                hospital_id="aiia-delhi",
                state=WorklistState.READY,
                intake_status=IntakeStatus.COMPLETE,
                arrived_at=BASE,
                chief_complaint="abdominal pain",
            )

    def test_the_worklist_itself_is_frozen(self) -> None:
        worklist = assemble([_entry()])
        with pytest.raises(ValueError):
            worklist.entries = ()  # type: ignore[misc]
        assert isinstance(worklist, Worklist)
