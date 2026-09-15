"""The queue is a triage surface, so its ordering rules are safety rules."""

from medikiosk.kiosk.queue import QueueStore, band_for, load_specialties


def report_for(specialty: str, priority: str, complaint: str = "chest pain") -> dict:
    return {
        "routing": {"queue": specialty, "priority": priority, "reason": "test"},
        "clinical": {"complaint": complaint},
    }


def test_an_emergency_leaves_the_queue_rather_than_topping_it() -> None:
    """Putting a possible MI at position one of a routine list still leaves them waiting behind
    whoever is in the room. Review cases are a separate list staff are expected to clear."""

    assert band_for({"priority": "emergency"}) == "review"
    assert band_for({"priority": "urgent"}) == "urgent"
    assert band_for({"priority": "routine"}) == "routine"
    assert band_for({}) == "routine"


def test_review_cases_sort_ahead_of_everyone_waiting(tmp_path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    store.assign("enc-routine", report_for("General Medicine", "routine", "fever"))
    store.assign("enc-urgent", report_for("Gastroenterology", "urgent", "abdominal pain"))
    store.assign("enc-review", report_for("Emergency", "emergency", "chest pain"))

    order = [entry.encounter_id for entry in store.waiting()]
    assert order[0] == "enc-review"
    assert order.index("enc-urgent") < order.index("enc-routine")


def test_numbering_runs_per_specialty_so_it_means_something_to_staff(tmp_path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    first = store.assign("a", report_for("Cardiology", "routine"))
    second = store.assign("b", report_for("Cardiology", "routine"))
    other = store.assign("c", report_for("Dermatology", "routine"))

    assert (first.number, second.number) == (1, 2)
    assert other.number == 1, "a different specialty starts its own numbering"


def test_assigning_the_same_encounter_twice_does_not_duplicate_it(tmp_path) -> None:
    """A reconnecting kiosk must not put the same patient in the queue again."""

    store = QueueStore(tmp_path / "queue.db")
    first = store.assign("enc-1", report_for("ENT", "routine"))
    again = store.assign("enc-1", report_for("ENT", "routine"))
    assert first.number == again.number
    assert len(store.waiting()) == 1


def test_state_changes_remove_a_patient_from_the_waiting_list(tmp_path) -> None:
    store = QueueStore(tmp_path / "queue.db")
    store.assign("enc-1", report_for("ENT", "routine"))
    store.set_state("enc-1", "IN_CONSULTATION")
    assert store.waiting() == []
    assert store.get("enc-1").state == "IN_CONSULTATION"


def test_specialties_fall_back_when_config_is_missing_or_broken(tmp_path) -> None:
    """A malformed hospital config must not take the kiosk down."""

    assert "General Medicine" in load_specialties(None)

    broken = tmp_path / "specialties.json"
    broken.write_text("{ not json", encoding="utf-8")
    assert "General Medicine" in load_specialties(broken)

    good = tmp_path / "good.json"
    good.write_text(
        '{"specialties": [{"name": "Cardiology", "enabled": true},'
        ' {"name": "Closed Dept", "enabled": false}]}',
        encoding="utf-8",
    )
    names = load_specialties(good)
    assert names == ["Cardiology"], "a disabled department must not be offered"
