"""Intake orchestration.

Binds the pure domain to persistence and events. The rule this module lives by:
every clinical decision is made in `app/domain`, and this layer only sequences
those decisions, writes the results and publishes what happened.

Nothing here decides what to ask, whether the history is complete, or whether a
red flag fires.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.content import ClinicalContent
from app.core.errors import ConflictError, ConsentError, NotFoundError, ValidationError
from app.core.ids import IdFactory, UuidIdFactory
from app.core.logging import get_logger
from app.domain.clinical.enums import (
    FactStatus,
    IntakeState,
    ReporterRole,
    Section,
    SourceType,
)
from app.domain.clinical.fact import ClinicalFact
from app.domain.clinical.patient_state import DocumentRecord, PatientIntakeState
from app.domain.clinical.provenance import (
    AlertId,
    CodedValue,
    FactId,
    PatientId,
    UserId,
)
from app.domain.contradictions.detector import Contradiction, detect
from app.domain.coverage.coverage import CoverageReport, compute
from app.domain.redflags.evaluator import RedFlagAlert, diff_alerts, evaluate
from app.domain.statemachine.engine import ClinicalStateMachine, Complete, Step
from app.domain.statemachine.policies import SelectionPolicy
from app.domain.summary.builder import ClinicalSummary, build
from app.events.bus import EventBus
from app.events.schemas import Event, EventName
from app.repositories.alerts import AlertRepository
from app.repositories.consent import ConsentRepository
from app.repositories.intakes import IntakeRepository
from app.services.answers import SubmittedAnswer, build_fact, is_decline, not_applicable_fact

logger = get_logger(__name__)

#: Purpose code the patient must grant before any history is recorded.
INTAKE_PURPOSE = "history_intake"
#: Purpose code gating raw audio retention. Separate from the base grant, and
#: off unless explicitly given.
AUDIO_RETENTION_PURPOSE = "raw_audio_retention"


@dataclass(frozen=True, slots=True)
class IntakeSnapshot:
    """Everything a caller needs after a state-changing operation."""

    state: PatientIntakeState
    next_step: Step | Complete
    coverage: CoverageReport
    alerts: tuple[RedFlagAlert, ...]
    newly_raised: tuple[RedFlagAlert, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()


class IntakeService:
    def __init__(
        self,
        *,
        intakes: IntakeRepository,
        alerts: AlertRepository,
        consent: ConsentRepository,
        content: ClinicalContent,
        bus: EventBus,
        settings: Settings | None = None,
        clock: Clock | None = None,
        ids: IdFactory | None = None,
    ) -> None:
        self._intakes = intakes
        self._alerts = alerts
        self._consent = consent
        self._content = content
        self._bus = bus
        self._settings = settings or get_settings()
        self._clock = clock or SystemClock()
        self._ids = ids or UuidIdFactory()
        self._machine = ClinicalStateMachine(
            content.content_set,
            SelectionPolicy(
                ask_optional_fields=self._settings.ask_optional_fields,
                max_optional_fields=self._settings.max_optional_fields,
                ayurveda_module_enabled=self._settings.ayurveda_module_enabled,
                supported_languages=tuple(self._settings.supported_languages),
            ),
        )

    @property
    def machine(self) -> ClinicalStateMachine:
        return self._machine

    @property
    def clock(self) -> Clock:
        return self._clock

    async def update_metadata(
        self,
        intake_id: str,
        *,
        language: str | None = None,
        reporter: ReporterRole | None = None,
        ayurveda_enabled: bool | None = None,
        patient_id: str | None = None,
    ) -> IntakeSnapshot:
        """Change session metadata. Never writes a clinical fact.

        Facts only ever come through `submit_answer`, which is the one path that
        builds provenance — there must be no second way in.
        """
        state = await self._intakes.require(intake_id)
        if language is not None:
            state = state.with_language(language)
        if reporter is not None:
            state = state.with_reporter(reporter)
        if ayurveda_enabled is not None:
            state = state.with_ayurveda(ayurveda_enabled)
        if patient_id is not None:
            state = state.with_patient(PatientId(patient_id))
        await self._intakes.save(state, now=self._clock.now())
        return await self._snapshot(state)

    # --- lifecycle ----------------------------------------------------------

    async def start(
        self,
        *,
        kiosk_id: str | None = None,
        department_code: str | None = None,
        patient_id: str | None = None,
        language: str | None = None,
    ) -> IntakeSnapshot:
        now = self._clock.now()
        intake_id = self._ids.new_id("intake")
        state = await self._intakes.create(
            intake_id=intake_id,
            started_at=now,
            kiosk_id=kiosk_id,
            department_code=department_code,
            patient_id=patient_id,
            language=language,
        )
        state = state.with_state(IntakeState.IDENTIFIED if patient_id else IntakeState.NOT_STARTED)
        if language:
            state = state.with_language(language)
        await self._intakes.save(state, now=now)
        await self._bus.publish(
            Event(
                name=EventName.INTAKE_STARTED,
                occurred_at=now,
                intake_id=intake_id,
                department_code=department_code,
                payload={"kiosk_id": kiosk_id or ""},
            )
        )
        return await self._snapshot(state)

    async def get(self, intake_id: str) -> IntakeSnapshot:
        state = await self._intakes.require(intake_id)
        return await self._snapshot(state)

    async def next_step(self, intake_id: str) -> Step | Complete:
        state = await self._intakes.require(intake_id)
        return self._machine.next_step(state)

    async def coverage(self, intake_id: str) -> CoverageReport:
        state = await self._intakes.require(intake_id)
        return compute(state, self._machine.plan(state))

    # --- answers -------------------------------------------------------------

    async def submit_answer(
        self,
        intake_id: str,
        answer: SubmittedAnswer,
        *,
        expected_revision: int | None = None,
    ) -> IntakeSnapshot:
        """Record one answer and return the updated state plus the next step."""
        state = await self._intakes.require(intake_id)
        self._require_consent_for_clinical_write(state, answer)
        if expected_revision is not None and expected_revision != state.revision:
            raise ConflictError(
                "intake revision mismatch; refresh before submitting",
                details={
                    "submitted_revision": expected_revision,
                    "current_revision": state.revision,
                },
            )

        now = self._clock.now()
        before_alerts = await self._alerts.list_for_intake(intake_id)

        if is_decline(answer):
            # A decline is recorded as a decline. It is neither an answer nor a gap.
            state = state.with_declined(answer.concept)
        else:
            # Resolved by concept rather than by "is this the current step", so a
            # section-at-a-time touch UI and a back-navigation correction both
            # get the answer shape the content actually declares.
            step = self._machine.step_for(state, answer.concept)
            fact = build_fact(
                answer,
                state,
                self._content.concepts,
                fact_id=self._ids.new_id("fact"),
                now=now,
                step=step,
            )
            state = self._apply_or_supersede(state, fact)
            state = self._apply_side_effects(state, answer, fact_status=fact.status)
            state = self._record_complaint_concept(state, fact, now=now)

        state = self._record_inapplicable(state, now=now)
        state = self._advance_lifecycle(state, now=now)
        await self._intakes.save(state, now=now)

        alerts, newly_raised = await self._evaluate_red_flags(state, before_alerts, now=now)
        await self._bus.publish(
            Event(
                name=EventName.INTAKE_UPDATED,
                occurred_at=now,
                intake_id=intake_id,
                payload={"concept": answer.concept, "revision": state.revision},
            )
        )
        if state.state is IntakeState.READY:
            await self._bus.publish(
                Event(name=EventName.INTAKE_READY, occurred_at=now, intake_id=intake_id)
            )
        return await self._snapshot(state, alerts=alerts, newly_raised=newly_raised)

    def _apply_or_supersede(
        self, state: PatientIntakeState, fact: ClinicalFact
    ) -> PatientIntakeState:
        """Apply a fact, superseding any live fact for the same concept.

        A correction is a new revision, never an edit. The old fact stays in the
        log, which is what makes "what did they say the first time?" answerable.
        """
        live = state.fact_for(fact.concept.concept_id)
        if live is None:
            return state.apply(fact)
        return state.apply(replace(fact, supersedes=live.fact_id))

    def _apply_side_effects(
        self, state: PatientIntakeState, answer: SubmittedAnswer, *, fact_status: FactStatus
    ) -> PatientIntakeState:
        """Session metadata that certain answers carry.

        The chief-complaint answer pins the pathway. That pin is explicit rather
        than recomputed, so a later correction to the complaint is a deliberate
        re-pin instead of the plan silently changing under the patient.
        """
        concept = answer.concept
        raw = answer.value

        if concept == "preferred_language" and isinstance(raw, str):
            state = state.with_language(raw)
        elif concept == "reporter_role" and isinstance(raw, str):
            try:
                state = state.with_reporter(ReporterRole(raw))
            except ValueError:
                logger.warning("unknown_reporter_role", concept=concept)
        elif (
            concept == self._content.content_set.chief_complaint_concept
            and fact_status is FactStatus.PRESENT
            and isinstance(raw, str)
        ):
            pathway = self._content.pathways.match_or_fallback(raw)
            state = state.with_pathway(pathway.pathway_id, pathway.review_of_systems)
        return state

    def _record_complaint_concept(
        self, state: PatientIntakeState, fact: ClinicalFact, *, now: datetime
    ) -> PatientIntakeState:
        """Record the presenting complaint as a fact about the complaint itself.

        `chief_complaint = chest_pain` says which pathway to run. It does not, on
        its own, say that the patient has chest pain — and the red-flag rules are
        written against the complaint concept, because that is how a clinician
        states the criterion. Without this, every complaint-anchored rule reads a
        concept nothing ever sets and can never fire.

        The derived fact inherits the answer's certainty and its verbatim words:
        it is a restatement, not a new claim, and it must not be more confident
        than what the patient actually said.
        """
        if fact.concept.concept_id != self._content.content_set.chief_complaint_concept:
            return state
        if fact.status is not FactStatus.PRESENT:
            return state
        value = fact.value
        complaint_id = value.code if isinstance(value, CodedValue) else None
        if complaint_id is None or complaint_id not in self._content.concepts:
            return state

        concept = self._content.concepts.require(complaint_id)
        derived = ClinicalFact(
            fact_id=FactId(self._ids.new_id("fact")),
            concept=concept.ref(),
            status=FactStatus.PRESENT,
            certainty=fact.certainty,
            temporality=fact.temporality,
            source_type=fact.source_type,
            source_ref=fact.source_ref,
            confidence=fact.confidence,
            reported_by=fact.reported_by,
            recorded_at=now,
            section=Section.CHIEF_COMPLAINT,
            original_expression=fact.original_expression,
            original_language=fact.original_language,
            note=f"derived from {fact.concept.concept_id}={complaint_id}",
        )
        return self._apply_or_supersede(state, derived)

    def _record_inapplicable(
        self, state: PatientIntakeState, *, now: datetime
    ) -> PatientIntakeState:
        """Mark fields whose precondition fails as NOT_APPLICABLE.

        Done eagerly so coverage has a real denominator and the report can say
        "not asked because the patient is male" rather than leaving a hole.
        """
        for planned, reason in self._machine.pending_not_applicable(state):
            state = state.apply(
                not_applicable_fact(
                    planned.concept,
                    planned.section,
                    self._content.concepts,
                    fact_id=self._ids.new_id("fact"),
                    now=now,
                    reason=reason,
                )
            )
        return state

    def _advance_lifecycle(
        self, state: PatientIntakeState, *, now: datetime
    ) -> PatientIntakeState:
        """Move the intake through its states.

        READY is reached only when coverage says every required field is settled.
        Never on a model's judgement, and never on a timer.
        """
        coverage = compute(state, self._machine.plan(state))
        if state.state in {IntakeState.NOT_STARTED, IntakeState.IDENTIFIED}:
            state = state.with_state(IntakeState.IN_PROGRESS)
        if not coverage.is_complete:
            if state.state in {IntakeState.READY, IntakeState.AWAITING_CONFIRMATION}:
                # A correction reopened a gap: go back to IN_PROGRESS rather than
                # letting a stale READY stand.
                state = state.with_state(IntakeState.IN_PROGRESS)
            return state
        if state.is_present("intake_confirmed"):
            return state.with_state(IntakeState.READY).with_timestamps(completed_at=now)
        if state.state is not IntakeState.AWAITING_CONFIRMATION:
            state = state.with_state(IntakeState.AWAITING_CONFIRMATION)
        return state

    # --- consent -------------------------------------------------------------

    def _require_consent_for_clinical_write(
        self, state: PatientIntakeState, answer: SubmittedAnswer
    ) -> None:
        """No clinical fact is recorded before consent is granted.

        The consent question itself and the identity questions that precede it
        are exempt — they are what get us to the consent decision.
        """
        pre_consent = {"preferred_language", "reporter_role", "age", "sex", "consent_given"}
        if answer.concept in pre_consent:
            return
        if state.consent_artefact_id is None:
            raise ConsentError(
                "consent has not been recorded for this intake",
                details={"intake_id": str(state.intake_id)},
            )

    async def record_consent(
        self,
        intake_id: str,
        *,
        language: str,
        granted_purposes: list[str],
        refused_purposes: list[str],
        granting_party: str,
        granting_party_name: str | None = None,
        audio_asset_id: str | None = None,
    ) -> str:
        """Write the consent artefact and link it to the intake.

        Refusing the base intake purpose is a valid outcome: the patient goes to
        the doctor without a kiosk history, and their place in the queue is
        untouched.
        """
        state = await self._intakes.require(intake_id)
        now = self._clock.now()
        consent_content = self._content.consent
        notice = consent_content.get("notice", {})
        notice_text = str(notice.get(language) or notice.get("en", ""))
        if not notice_text:
            raise ValidationError(f"no consent notice available in language '{language}'")

        artefact_id = self._ids.new_id("consent")
        await self._consent.record(
            artefact_id=artefact_id,
            intake_id=intake_id,
            patient_id=str(state.patient_id) if state.patient_id else None,
            consent_version=str(consent_content.get("version", "1")),
            language=language,
            notice_text=notice_text,
            granted_purposes=granted_purposes,
            refused_purposes=refused_purposes,
            granting_party=granting_party,
            granting_party_name=granting_party_name,
            granted_at=now,
            audio_asset_id=audio_asset_id,
        )
        if INTAKE_PURPOSE in granted_purposes:
            state = state.with_consent(artefact_id).with_state(IntakeState.CONSENTED)
        else:
            state = state.with_state(IntakeState.ABANDONED)
        await self._intakes.save(state, now=now)
        return artefact_id

    async def audio_retention_permitted(self, intake_id: str) -> bool:
        """Both the facility setting and the patient's own grant must say yes."""
        if not self._settings.raw_audio_retention_enabled:
            return False
        return await self._consent.has_purpose(intake_id, AUDIO_RETENTION_PURPOSE)

    # --- confirmation and verification ---------------------------------------

    async def confirm(
        self, intake_id: str, *, corrections: list[str] | None = None
    ) -> IntakeSnapshot:
        """The patient reviews what we recorded and confirms or corrects it.

        Confirmation raises certainty on the facts they re-affirmed — the one
        legitimate promotion in the system, because a human did it — and does
        not touch `physician_verified`.
        """
        state = await self._intakes.require(intake_id)
        now = self._clock.now()
        to_correct = set(corrections or ())

        for fact in state.current():
            if fact.concept.concept_id in to_correct or fact.patient_confirmed:
                continue
            if fact.status in {FactStatus.NOT_ASKED, FactStatus.NOT_APPLICABLE}:
                continue
            if fact.source_type is SourceType.DERIVED:
                continue
            state = state.apply(
                fact.confirmed_by_patient(
                    new_fact_id=self._ids.new_id("fact"), recorded_at=now
                )
            )

        if to_correct:
            # Corrections reopen the intake: the concepts named are cleared back
            # to unasked so the state machine puts them again.
            state = state.with_state(IntakeState.IN_PROGRESS)
        else:
            state = self._advance_lifecycle(state, now=now)

        await self._intakes.save(state, now=now)
        await self._bus.publish(
            Event(
                name=EventName.INTAKE_CONFIRMED,
                occurred_at=now,
                intake_id=intake_id,
                payload={"corrections": len(to_correct)},
            )
        )
        return await self._snapshot(state)

    async def physician_verify(
        self, intake_id: str, *, physician_id: UserId, concepts: list[str] | None = None
    ) -> IntakeSnapshot:
        """A physician signs off facts. Records who, on every fact touched.

        Patient confirmation and physician verification are separate flags and
        neither implies the other: a patient can be certain and wrong, and a
        physician can verify a fact the patient never confirmed.
        """
        state = await self._intakes.require(intake_id)
        now = self._clock.now()
        wanted = set(concepts) if concepts else None

        for fact in state.current():
            if fact.physician_verified:
                continue
            if wanted is not None and fact.concept.concept_id not in wanted:
                continue
            if fact.status in {FactStatus.NOT_ASKED, FactStatus.NOT_APPLICABLE}:
                continue
            state = state.apply(
                fact.verified_by_physician(
                    new_fact_id=self._ids.new_id("fact"),
                    recorded_at=now,
                    physician_id=str(physician_id),
                )
            )
        await self._intakes.save(state, now=now)
        await self._bus.publish(
            Event(
                name=EventName.REPORT_PHYSICIAN_VERIFIED,
                occurred_at=now,
                intake_id=intake_id,
                actor_id=str(physician_id),
            )
        )
        return await self._snapshot(state)

    # --- documents ------------------------------------------------------------

    async def attach_document(
        self, intake_id: str, *, document_id: str, kind: str, uploaded_at: datetime
    ) -> PatientIntakeState:
        state = await self._intakes.require(intake_id)
        state = state.with_document(
            DocumentRecord(document_id=document_id, kind=kind, uploaded_at=uploaded_at)
        )
        await self._intakes.save(state, now=self._clock.now())
        await self._bus.publish(
            Event(
                name=EventName.DOCUMENT_UPLOADED,
                occurred_at=uploaded_at,
                intake_id=intake_id,
                document_id=document_id,
                payload={"kind": kind},
            )
        )
        return state

    async def apply_document_extraction(
        self,
        intake_id: str,
        *,
        document_id: str,
        facts: tuple[Any, ...],
        low_confidence: bool,
        page_count: int,
        kind: str,
    ) -> IntakeSnapshot:
        """Fold OCR-derived facts into the record.

        They enter as DOCUMENT-sourced and unverified, and they do not supersede
        what the patient said. Both sides stay live so the contradiction detector
        can find the disagreement — which is the entire point of scanning the
        old prescription in the first place.
        """
        state = await self._intakes.require(intake_id)
        now = self._clock.now()
        for fact in facts:
            # `apply_record` puts the fact in the live view only when the patient
            # has not already answered that concept. Where they have, both facts
            # survive and the contradiction detector reports the disagreement.
            state = state.apply_record(fact)

        state = state.with_document(
            DocumentRecord(
                document_id=document_id,
                kind=kind,
                uploaded_at=now,
                processed=True,
                page_count=page_count,
                low_confidence=low_confidence,
            )
        )
        await self._intakes.save(state, now=now)
        await self._bus.publish(
            Event(
                name=EventName.DOCUMENT_PROCESSED,
                occurred_at=now,
                intake_id=intake_id,
                document_id=document_id,
                payload={"facts": len(facts), "low_confidence": low_confidence},
            )
        )
        if low_confidence:
            await self._bus.publish(
                Event(
                    name=EventName.DOCUMENT_LOW_CONFIDENCE,
                    occurred_at=now,
                    intake_id=intake_id,
                    document_id=document_id,
                )
            )
        return await self._snapshot(state)

    # --- red flags -------------------------------------------------------------

    async def _evaluate_red_flags(
        self,
        state: PatientIntakeState,
        before: tuple[RedFlagAlert, ...],
        *,
        now: datetime,
    ) -> tuple[tuple[RedFlagAlert, ...], tuple[RedFlagAlert, ...]]:
        """Evaluate, persist newly raised alerts, publish.

        Note what does not happen: no queue is touched. An alert asks a human to
        look, and their acknowledgement is what permits anything else.
        """
        current = evaluate(state, self._content.red_flags)
        raised, _cleared = diff_alerts(before, current)
        identified = tuple(
            alert.with_identity(AlertId(self._ids.new_id("alert")), now) for alert in raised
        )
        stored = await self._alerts.raise_alerts(identified, intake_id=str(state.intake_id))
        for alert in stored:
            await self._bus.publish(
                Event(
                    name=EventName.REDFLAG_RAISED,
                    occurred_at=now,
                    intake_id=str(state.intake_id),
                    alert_id=str(alert.alert_id),
                    payload={
                        "rule_id": alert.rule_id,
                        "severity": alert.severity.value,
                        "notify": alert.action.notify,
                        "priority_hint": alert.action.priority_hint or "",
                    },
                )
            )
        return await self._alerts.list_for_intake(str(state.intake_id)), stored

    async def acknowledge_alert(
        self, alert_id: str, *, user_id: UserId
    ) -> RedFlagAlert:
        now = self._clock.now()
        alert = await self._alerts.acknowledge(alert_id, user_id=user_id, now=now)
        await self._bus.publish(
            Event(
                name=EventName.REDFLAG_ACKNOWLEDGED,
                occurred_at=now,
                alert_id=alert_id,
                actor_id=str(user_id),
                payload={"rule_id": alert.rule_id, "severity": alert.severity.value},
            )
        )
        return alert

    async def dismiss_alert(
        self, alert_id: str, *, user_id: UserId, reason: str
    ) -> RedFlagAlert:
        now = self._clock.now()
        alert = await self._alerts.dismiss(alert_id, user_id=user_id, now=now, reason=reason)
        await self._bus.publish(
            Event(
                name=EventName.REDFLAG_DISMISSED,
                occurred_at=now,
                alert_id=alert_id,
                actor_id=str(user_id),
                payload={"rule_id": alert.rule_id},
            )
        )
        return alert

    # --- reporting -------------------------------------------------------------

    async def summary(self, intake_id: str) -> ClinicalSummary:
        state = await self._intakes.require(intake_id)
        alerts = await self._alerts.list_for_intake(intake_id)
        coverage = compute(state, self._machine.plan(state))
        return build(
            state,
            coverage=coverage,
            conflicts=detect(state),
            alerts=alerts,
        )

    async def evidence_for(self, intake_id: str, fact_id: str) -> dict[str, Any]:
        """Provenance for one fact, including its supersession chain.

        This is what turns a line of the report into evidence: the physician
        clicks a statement and lands on the transcript offset or the region of
        the scan it came from.
        """
        state = await self._intakes.require(intake_id)
        fact = state.by_id(FactId(fact_id))
        if fact is None:
            raise NotFoundError(f"fact {fact_id} not found in intake {intake_id}")
        chain = state.history_of(fact.concept.concept_id)
        return {
            "fact_id": str(fact.fact_id),
            "concept": fact.concept.concept_id,
            "status": fact.status.value,
            "certainty": fact.certainty.value,
            "value": fact.rendered_value(),
            "original_expression": fact.original_expression,
            "original_language": fact.original_language,
            "source_type": fact.source_type.value,
            "source_ref": _source_ref_payload(fact.source_ref),
            "confidence": fact.confidence,
            "reported_by": fact.reported_by.value,
            "patient_confirmed": fact.patient_confirmed,
            "physician_verified": fact.physician_verified,
            "recorded_at": fact.recorded_at.isoformat(),
            "revisions": [
                {
                    "fact_id": str(r.fact_id),
                    "status": r.status.value,
                    "value": r.rendered_value(),
                    "recorded_at": r.recorded_at.isoformat(),
                    "supersedes": str(r.supersedes) if r.supersedes else None,
                }
                for r in chain
            ],
        }

    # --- housekeeping ------------------------------------------------------------

    async def abandon_stale(self) -> tuple[str, ...]:
        """Mark inactive sessions abandoned and drop their kiosk linkage.

        A patient who walked away must not leave their history reachable from the
        terminal they were standing at.
        """
        now = self._clock.now()
        cutoff = now - timedelta(seconds=self._settings.intake_inactivity_timeout_seconds)
        stale = await self._intakes.list_stale(
            before=cutoff,
            states=(
                IntakeState.NOT_STARTED,
                IntakeState.IDENTIFIED,
                IntakeState.CONSENTED,
                IntakeState.IN_PROGRESS,
                IntakeState.AWAITING_CONFIRMATION,
            ),
        )
        for intake_id in stale:
            state = await self._intakes.require(intake_id)
            partial = len(state.current()) > 0
            state = state.with_state(
                IntakeState.PARTIAL if partial else IntakeState.ABANDONED
            )
            await self._intakes.save(state, now=now)
            await self._intakes.purge_session_state(intake_id)
            await self._bus.publish(
                Event(
                    name=EventName.INTAKE_ABANDONED,
                    occurred_at=now,
                    intake_id=intake_id,
                    payload={"partial": partial},
                )
            )
        return stale

    async def teardown_kiosk_session(self, kiosk_id: str) -> tuple[str, ...]:
        """Detach every intake from a kiosk. Called on session end.

        After this, no request carrying only the kiosk id can reach the previous
        patient's intake.
        """
        intake_ids = await self._intakes.find_by_kiosk(kiosk_id)
        for intake_id in intake_ids:
            await self._intakes.purge_session_state(str(intake_id))
        return tuple(str(i) for i in intake_ids)

    # --- internals ---------------------------------------------------------------

    async def _snapshot(
        self,
        state: PatientIntakeState,
        *,
        alerts: tuple[RedFlagAlert, ...] | None = None,
        newly_raised: tuple[RedFlagAlert, ...] = (),
    ) -> IntakeSnapshot:
        if alerts is None:
            alerts = await self._alerts.list_for_intake(str(state.intake_id))
        return IntakeSnapshot(
            state=state,
            next_step=self._machine.next_step(state),
            coverage=compute(state, self._machine.plan(state)),
            alerts=alerts,
            newly_raised=newly_raised,
            contradictions=detect(state),
        )


def _source_ref_payload(ref: Any) -> dict[str, Any]:
    if ref.transcript is not None:
        return {
            "kind": "transcript",
            "segment_id": str(ref.transcript.segment_id),
            "start_ms": ref.transcript.start_ms,
            "end_ms": ref.transcript.end_ms,
        }
    if ref.document is not None:
        bbox = ref.document.bbox
        return {
            "kind": "document",
            "document_id": str(ref.document.document_id),
            "page": ref.document.page,
            "bbox": (
                None
                if bbox is None
                else {"x": bbox.x, "y": bbox.y, "width": bbox.width, "height": bbox.height}
            ),
        }
    return {"kind": "actor", "entered_by": ref.entered_by}
