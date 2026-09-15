"""A pending question must not turn ordinary grammar into a clinical fact.

The Hindi copula "है" ends a large share of normal sentences. While it lived in the
match-anywhere affirmative set, "मेरी उम्र चालीस साल है" set vomiting=true and
"दर्द बहुत तेज़ है" set active_bleeding=true, which raised an emergency staff alert for a
patient who never mentioned bleeding.
"""

import pytest

from medikiosk.clinical.answers import direct_answer
from medikiosk.clinical.questions import QUESTIONS


def question(question_id: str):
    return QUESTIONS[question_id]


@pytest.mark.parametrize(
    ("question_id", "transcript", "language"),
    [
        ("ask_vomiting", "मेरी उम्र चालीस साल है", "hi"),
        ("ask_bleeding", "दर्द बहुत तेज़ है", "hi"),
        ("ask_bleeding", "मुझे दो दिन से बुखार है", "hi"),
        ("ask_vomiting", "माझे वय चाळीस वर्षे आहे", "mr"),
        ("ask_bleeding", "મારી ઉંમર ચાલીસ વર્ષ છે", "gu"),
    ],
)
def test_sentence_ending_in_copula_is_not_agreement(question_id, transcript, language):
    assert direct_answer(question(question_id), transcript, language) == {}


@pytest.mark.parametrize(
    ("transcript", "language"),
    [("है", "hi"), ("जी है", "hi"), ("हाँ", "hi"), ("आहे", "mr"), ("છે", "gu"), ("yes", "en")],
)
def test_bare_agreement_still_binds(transcript, language):
    assert direct_answer(question("ask_bleeding"), transcript, language) == {
        "active_bleeding": True
    }


@pytest.mark.parametrize(
    ("transcript", "language"),
    [("नहीं", "hi"), ("no", "en"), ("मुझे कहीं से खून नहीं बह रहा", "hi")],
)
def test_denial_still_binds(transcript, language):
    assert direct_answer(question("ask_bleeding"), transcript, language) == {
        "active_bleeding": False
    }
