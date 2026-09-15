import pytest

from medikiosk.kiosk.protocol import FlowAction, SessionGuard


def action(guard, **changes):
    return FlowAction.model_validate({"type": "flow.action", "session_id": guard.session_id,
                                      "revision": guard.revision, "action_id": "one",
                                      "action": "choose", "value": "en", **changes})


def test_retry_is_not_a_second_action():
    guard = SessionGuard()
    first = action(guard)
    assert guard.check(first)
    guard.accept(first)
    guard.invalidate_prompt()
    assert guard.check(first) is False
    with pytest.raises(ValueError):
        guard.check(first.model_copy(update={"value": "hi"}))


def test_stale_and_other_patient_actions_are_rejected():
    guard = SessionGuard()
    stale = action(guard)
    guard.invalidate_prompt()
    with pytest.raises(ValueError):
        guard.check(stale)
    with pytest.raises(ValueError):
        guard.check(action(guard, session_id=SessionGuard().session_id))


def test_resume_changes_prompt_epoch_without_losing_deduplication():
    guard = SessionGuard()
    first = action(guard)
    guard.accept(first)
    resumed = SessionGuard(guard.session_id, guard.token)
    resumed.restore(guard.snapshot())
    assert resumed.revision > guard.revision
    assert resumed.check(first) is False
    assert guard.token not in str(guard.snapshot())
    assert resumed.owns(guard.session_id, guard.token)
    assert not resumed.owns(guard.session_id, guard.session_id)
