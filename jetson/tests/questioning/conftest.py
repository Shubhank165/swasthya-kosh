"""Shared fixtures for the questioning agent's tests.

The agent is loaded once per session. It reads content off disk and holds no
mutable state of its own — every test brings its own `PatientState`, which is
the whole reason the engine was built as a function of one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from questioning_agent.core.agent import QuestioningAgent
from questioning_agent.core.patient_state import PatientState
from questioning_agent.knowledge.information_schema import SlotRegistry
from questioning_agent.localization.languages import Vocabularies

CONTENT = Path(__file__).resolve().parents[2] / "clinical" / "questioning"


@pytest.fixture(scope="session")
def agent() -> QuestioningAgent:
    return QuestioningAgent.load(CONTENT)


@pytest.fixture(scope="session")
def slots() -> SlotRegistry:
    return SlotRegistry.load(CONTENT)


@pytest.fixture(scope="session")
def vocabularies() -> Vocabularies:
    return Vocabularies.load(CONTENT)


@pytest.fixture
def english(vocabularies: Vocabularies):  # type: ignore[no-untyped-def]
    return vocabularies["en"]


@pytest.fixture
def hindi(vocabularies: Vocabularies):  # type: ignore[no-untyped-def]
    return vocabularies["hi"]


def started(
    agent: QuestioningAgent,
    complaints: list[str],
    chief: str | None = None,
    *,
    timeline: str = "three days ago",
    language: str = "en",
) -> PatientState:
    """A state that has been through the fixed three and no further.

    Every adaptive test starts here, because every adaptive question depends on
    the domains those three establish.
    """
    state = PatientState()
    for _ in range(3):
        turn = agent.next(state, language=language)
        assert turn is not None, "the fixed three should always be offered"
        if turn.id == "fixed.complaints":
            reply = ", ".join(complaints)
        elif turn.id == "fixed.chief_complaint":
            reply = chief or complaints[0]
        else:
            reply = timeline
        agent.answer(state, turn, reply, language=language)
    return state


def ask_all(
    agent: QuestioningAgent,
    state: PatientState,
    answers: dict[str, str],
    *,
    limit: int = 40,
    language: str = "en",
) -> list[str]:
    """Run to completion, answering from `answers` and skipping the rest.

    Skipping the unanswered ones rather than inventing replies keeps a test
    about question *selection* from accidentally being a test of the parser.
    """
    asked: list[str] = []
    for _ in range(limit):
        turn = agent.next(state, language=language)
        if turn is None:
            break
        asked.append(turn.id)
        reply = answers.get(turn.id)
        if reply is None:
            agent.skip(state, turn)
        else:
            agent.answer(state, turn, reply, language=language)
    return asked
