"""Why one question beats another — §11.

A weighted sum of six terms, every one of which is a number somebody can check
on paper. There is no model here and there is not going to be one: a
questionnaire that cannot say why it asked something is a questionnaire nobody
can review, and this content is going in front of clinicians who will want to
argue with it.

The weights live in one dataclass rather than scattered through the arithmetic,
so tuning is an edit in one place and a test can pin a weighting it cares about
without touching the engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.questioning_agent.core.patient_state import PatientState
from app.questioning_agent.core.schemas import QuestionDecision
from app.questioning_agent.knowledge.information_schema import SlotRegistry
from app.questioning_agent.questioning.candidate_generator import Candidate


@dataclass(frozen=True, slots=True)
class Weights:
    """The coefficients. Configurable rather than hardcoded — §11."""

    coverage: float = 2.0
    priority: float = 3.0
    chief_complaint: float = 3.0
    cross_domain: float = 2.0
    required: float = 4.0
    burden: float = 1.0

    #: Below this, the selector stops rather than scraping the barrel. An intake
    #: that runs until it has asked everything is the thing being replaced.
    #:
    #: 12 was chosen by looking at where the ranking stops being worth a screen.
    #: For a patient whose only complaint is poor sleep it ends the interview at
    #: 22 questions; what falls below the line is family history, past surgery,
    #: alcohol and the peripheral AYUSH items — real questions, none of which
    #: changes what a practitioner does about insomnia. Every slot marked
    #: `required` scores in the twenties and clears it comfortably, which is what
    #: makes the floor safe to set at all.
    #:
    #: It is a coefficient, not a question count. Somebody with four complaints
    #: is asked more because more of what they could be asked is worth asking,
    #: which is the behaviour a fixed budget cannot produce.
    floor: float = 12.0


DEFAULT_WEIGHTS = Weights()


def score(
    candidate: Candidate,
    state: PatientState,
    slots: SlotRegistry,
    weights: Weights = DEFAULT_WEIGHTS,
) -> QuestionDecision:
    """Score one candidate, keeping the reasons.

    The reasons are not decoration. §30 asks for an explanation of every
    selection, and building it here — where the numbers are — is the only place
    it can be right; reconstructing it afterwards would be a second
    implementation of the same logic, free to disagree.
    """
    question = candidate.question
    reasons: list[str] = []

    # 1. Coverage. How many unknown slots this fills, and the reason a merged
    #    question beats three separate ones without anything knowing about
    #    merging.
    coverage = float(candidate.coverage)
    if coverage > 1:
        reasons.append(f"fills {int(coverage)} unknown slots at once")

    # 2. Clinical priority. The mean of the slots' own priorities rather than
    #    the maximum: a question that fills one important slot and three trivial
    #    ones is not as valuable as one that fills two important ones, and the
    #    maximum cannot tell them apart. Normalised to 0-1 so the weights stay
    #    comparable.
    priorities = [
        slot.priority for target in candidate.targets if (slot := slots.get(target))
    ]
    priority = (sum(priorities) / len(priorities) / 10.0) if priorities else 0.5
    if priority >= 0.8:
        reasons.append("high clinical priority")

    # 3. Chief complaint relevance. What the patient said was worst gets asked
    #    about first — which is both clinically right and the thing that makes
    #    the interview feel like it is listening.
    chief = 0.0
    if state.chief_complaint:
        touching = sum(
            1 for target in candidate.targets if target.startswith(f"{state.chief_complaint}.")
        )
        if touching:
            chief = touching / max(1, candidate.coverage)
            reasons.append(f"about {state.chief_complaint}, the main complaint")

    # 4. Cross-domain value. A question spanning several active domains is worth
    #    more than the sum of its parts, because the alternative is several
    #    screens.
    domains = {target.split(".", 1)[0] for target in candidate.targets}
    cross = float(len(domains) - 1) if len(domains) > 1 else 0.0
    if cross:
        reasons.append(f"covers {len(domains)} domains in one question")

    # 5. Required. The floor a case cannot go below — medication, allergies, age
    #    — regardless of what the patient came in with.
    required = sum(
        1 for target in candidate.targets if (slot := slots.get(target)) and slot.required
    )
    if required:
        reasons.append("part of the history asked of every patient")

    # 6. Burden, subtracted. Fifteen checkboxes is not the same ask as a yes/no.
    burden = float(question.burden)

    total = (
        weights.coverage * coverage
        + weights.priority * priority * question.priority
        + weights.chief_complaint * chief
        + weights.cross_domain * cross
        + weights.required * float(required)
        - weights.burden * burden
    )

    if not reasons:
        reasons.append(f"{candidate.targets[0]} is unknown")
    reasons.append("not previously asked")

    return QuestionDecision(
        question_id=question.id,
        score=round(total, 3),
        reasons=tuple(reasons),
        targets=candidate.targets,
    )


__all__ = ["DEFAULT_WEIGHTS", "Weights", "score"]
