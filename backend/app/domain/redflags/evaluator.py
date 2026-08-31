"""Red-flag evaluation.

`evaluate` is a pure function: same facts in, same alerts out, forever. No model
participates, and the result never touches the queue. An alert is a request for
a human to look; the human's acknowledgement is what authorises anything else.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.clinical.enums import Severity, severity_rank
from app.domain.clinical.patient_state import PatientIntakeState
from app.domain.clinical.provenance import AlertId, FactId, UserId
from app.domain.redflags.rules import SAFE_LABEL, RedFlagAction, RedFlagRule, RedFlagRuleSet


@dataclass(frozen=True, slots=True)
class RedFlagAlert:
    """A fired rule, with the facts that fired it.

    `supporting_facts` is what lets triage see the basis in one click instead of
    trusting the alert. `patient_safe_label` is the only string that may be shown
    on a patient-facing surface.
    """

    rule_id: str
    severity: Severity
    label: str
    action: RedFlagAction
    clinical_source: str
    supporting_facts: tuple[FactId, ...]
    criteria_description: str
    rule_version: int = 1
    alert_id: AlertId | None = None
    raised_at: datetime | None = None
    acknowledged_by: UserId | None = None
    acknowledged_at: datetime | None = None
    dismissed_by: UserId | None = None
    dismissed_at: datetime | None = None
    dismissal_reason: str | None = None

    @property
    def patient_safe_label(self) -> str:
        return SAFE_LABEL

    @property
    def is_acknowledged(self) -> bool:
        return self.acknowledged_by is not None

    @property
    def is_dismissed(self) -> bool:
        return self.dismissed_by is not None

    @property
    def is_open(self) -> bool:
        return not self.is_acknowledged and not self.is_dismissed

    def acknowledged(self, *, by: UserId, at: datetime) -> RedFlagAlert:
        """Record the human who took responsibility for this alert.

        Only an acknowledged alert may be cited by `Ticket.escalate`.
        """
        if self.is_dismissed:
            raise ValueError(f"alert {self.rule_id} was dismissed and cannot be acknowledged")
        return replace(self, acknowledged_by=by, acknowledged_at=at)

    def dismissed(self, *, by: UserId, at: datetime, reason: str) -> RedFlagAlert:
        if self.is_acknowledged:
            raise ValueError(f"alert {self.rule_id} was acknowledged and cannot be dismissed")
        if not reason:
            raise ValueError("dismissing an alert requires a reason")
        return replace(self, dismissed_by=by, dismissed_at=at, dismissal_reason=reason)

    def with_identity(self, alert_id: AlertId, raised_at: datetime) -> RedFlagAlert:
        return replace(self, alert_id=alert_id, raised_at=raised_at)


def supporting_fact_ids(
    state: PatientIntakeState, rule: RedFlagRule
) -> tuple[FactId, ...]:
    """Live fact ids for the concepts the rule reads, in stable concept order.

    Includes every concept the criteria mentions that has a fact, not only those
    that happened to be true — a physician reviewing an alert needs the negative
    limbs too.
    """
    return tuple(
        fact.fact_id
        for concept_id in sorted(rule.concepts())
        if (fact := state.fact_for(concept_id)) is not None
    )


def evaluate(state: PatientIntakeState, rules: RedFlagRuleSet) -> tuple[RedFlagAlert, ...]:
    """Every rule whose criteria hold, most severe first.

    Deliberately tuned for recall: rules are written to over-fire and are tuned
    down with clinicians. A false alert costs a triage nurse thirty seconds; a
    missed one is not recoverable.
    """
    alerts = [
        RedFlagAlert(
            rule_id=rule.rule_id,
            severity=rule.severity,
            label=rule.label,
            action=rule.action,
            clinical_source=rule.clinical_source,
            supporting_facts=supporting_fact_ids(state, rule),
            criteria_description=rule.criteria.describe(),
            rule_version=rule.version,
        )
        for rule in rules
        if rule.matches(state)
    ]
    return tuple(sorted(alerts, key=lambda a: (-severity_rank(a.severity), a.rule_id)))


def diff_alerts(
    previous: Sequence[RedFlagAlert], current: Sequence[RedFlagAlert]
) -> tuple[tuple[RedFlagAlert, ...], tuple[RedFlagAlert, ...]]:
    """(newly raised, no longer firing), by rule id.

    The service layer emits `intake.redflag.raised` only for the newly raised set,
    so a patient does not get re-alerted on every answer. Alerts that stop firing
    are reported but never silently retracted — a raised alert stays on the record.
    """
    previous_ids = {a.rule_id for a in previous}
    current_ids = {a.rule_id for a in current}
    raised = tuple(a for a in current if a.rule_id not in previous_ids)
    cleared = tuple(a for a in previous if a.rule_id not in current_ids)
    return raised, cleared


def highest_severity(alerts: Sequence[RedFlagAlert]) -> Severity | None:
    """Most severe open alert, for dashboard ordering."""
    open_alerts = [a for a in alerts if a.is_open]
    if not open_alerts:
        return None
    return max((a.severity for a in open_alerts), key=severity_rank)


@dataclass(frozen=True, slots=True)
class RedFlagReport:
    """Evaluation result plus the coverage of the screen itself.

    `unscreened_concepts` matters: a rule that reads a concept nobody asked about
    can never fire, and that is a content bug, not a quiet negative.
    """

    alerts: tuple[RedFlagAlert, ...] = field(default_factory=tuple)
    unscreened_concepts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_critical(self) -> bool:
        return any(a.severity is Severity.CRITICAL for a in self.alerts)


def evaluate_with_coverage(
    state: PatientIntakeState, rules: RedFlagRuleSet
) -> RedFlagReport:
    """Evaluate, and report which rule concepts were never put to the patient."""
    unscreened = tuple(
        sorted(concept for concept in rules.concepts() if not state.is_answered(concept))
    )
    return RedFlagReport(alerts=evaluate(state, rules), unscreened_concepts=unscreened)
