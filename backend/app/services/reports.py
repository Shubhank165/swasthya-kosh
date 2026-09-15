"""Report generation and physician verification — §7.

The report is assembled by `app.domain.report.builder`, which is pure. This
service does the I/O around it: load the record, load the extractions, recompute
contradictions, resolve the interaction findings, persist the result.

Contradictions are **recomputed on every read** rather than stored with the
record. A document that arrives an hour after ingest changes what conflicts, and
recomputing means the physician sees today's answer against today's evidence
without anything being re-ingested.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from app.core.clock import Clock
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.ids import IdFactory
from app.core.logging import get_logger
from app.domain.ayush_profile import AyushProfileSnapshot
from app.domain.clinical.enums import Section
from app.domain.contradictions import detector
from app.domain.documents.alignment import align_medications
from app.domain.documents.extraction import (
    DocumentExtraction,
)
from app.domain.documents.ingredients import IngredientIndex
from app.domain.documents.interactions import InteractionFinding, InteractionTable
from app.domain.record import (
    CanonicalRecord,
    Fact,
    FactValue,
    PatientRefType,
    PhysicianAction,
)
from app.domain.report import builder
from app.domain.report.builder import FieldLabels
from app.domain.report.model import PhysicianReport, ReportBundle
from app.domain.report.templates import TemplateRegistry
from app.domain.timeline.fallback import deterministic_timeline
from app.domain.timeline.model import TimelineSnapshot
from app.events.bus import EventBus
from app.events.schemas import Event, EventName
from app.repositories.ayush_profiles import AyushProfileRepository, snapshot_of
from app.repositories.consent import AuditRepository, ReportRepository
from app.repositories.documents import DocumentRepository
from app.repositories.intakes import IntakeRepository
from app.repositories.patients import PatientLinkRepository
from app.services.timeline import TimelineService

logger = get_logger(__name__)


class ReportService:
    """Builds, stores and serves the physician report."""

    def __init__(
        self,
        *,
        intakes: IntakeRepository,
        documents: DocumentRepository,
        reports: ReportRepository,
        audit: AuditRepository,
        templates: TemplateRegistry,
        labels: FieldLabels,
        interactions: InteractionTable,
        ingredients: IngredientIndex,
        bus: EventBus,
        clock: Clock,
        ids: IdFactory,
        links: PatientLinkRepository | None = None,
        timeline: TimelineService | None = None,
        ayush_profiles: AyushProfileRepository | None = None,
        max_prior_intakes: int = 5,
        facility_timezone: str = "Asia/Kolkata",
        demo: bool = False,
    ) -> None:
        self._intakes = intakes
        self._documents = documents
        self._reports = reports
        self._audit = audit
        self._templates = templates
        self._labels = labels
        self._interactions = interactions
        self._ingredients = ingredients
        self._bus = bus
        self._clock = clock
        self._ids = ids
        self._links = links
        self._timeline = timeline
        self._ayush_profiles = ayush_profiles
        self._max_prior_intakes = max_prior_intakes
        self._timezone = facility_timezone
        self._demo = demo

    async def load_record(self, *, hospital_id: str, intake_id: str) -> CanonicalRecord:
        """The canonical record with contradictions recomputed.

        Medication aliases are derived first, so a spoken "Metformin" and a
        printed "Tab. Metformin 900.2 mg BD" compare on the same field and the
        dose discrepancy is reported — rather than the prescription showing up
        as a medicine the patient failed to mention, which they did not.

        The aliases are not persisted. They are derived on every read, so a
        change to the ingredient table applies to records already stored.
        """
        record = await self._intakes.load(hospital_id=hospital_id, intake_id=intake_id)
        live = record.live_facts()
        aligned = (*live, *align_medications(live, self._ingredients))
        conflicts = detector.detect(aligned, labels=self._labels_map())
        return record.model_copy(update={"contradictions": list(conflicts)})

    def _labels_map(self) -> dict[str, str]:
        return self._labels.as_mapping()

    async def _timeline_for(
        self,
        record: CanonicalRecord,
        extractions: Sequence[DocumentExtraction],
        language: str,
    ) -> TimelineSnapshot:
        """The dated history for this intake.

        With no provider configured — the default — this is the **deterministic**
        timeline: pure code over the patient's prior records at this hospital,
        plus whatever their uploaded documents were dated. No model, no
        configuration, and it already meets the problem statement's
        dated-history requirement. A provider only ever narrows it.

        Prior visits are found through the patient's whole alias set, so the
        history a timeline is built from is the same history `/patients/history`
        returns: an ABHA address and a phone number do not produce two different
        timelines for one person.

        A patient with no reference — a guest — has no prior records to walk,
        and gets an empty timeline rather than a pending one. Nothing is coming
        later for them, and `history_pending` would be a promise.
        """
        prior = await self._prior_records(record)
        if self._timeline is None:
            return deterministic_timeline(prior, extractions)
        return await self._timeline.build(
            record, prior=prior, extractions=extractions, language=language
        )

    async def _ayush_profile_for(
        self, record: CanonicalRecord
    ) -> AyushProfileSnapshot | None:
        """The patient's AYUSH module answers, if they have filled it.

        **This is where the reading happens, and it happens here on purpose.**
        The builder is pure and byte-deterministic — that is what lets the
        golden files hold it true — so it is handed a finished value and never
        a repository, exactly as `_timeline_for` hands it a `TimelineSnapshot`.

        `None` on three paths that mean different things to nobody downstream:
        no repository configured, a guest with no patient reference, or a
        patient who has not filled the module. All three render as an Ayurveda
        section without profile lines, which is what "we do not have this" looks
        like.

        A guest is excluded rather than looked up. `guest` is not an identity —
        it is the absence of one — so expanding it through the link table would
        match every other guest at this hospital and hand one patient's
        constitution to another.
        """
        if self._ayush_profiles is None:
            return None
        ref = record.patient_ref
        if ref is None or not ref.value or ref.type is PatientRefType.GUEST:
            return None
        # Expanded through the link table, exactly as `_prior_records` does.
        # The profile is filed under whichever reference the patient's session
        # carried — `phone`, today — and this visit may be filed under another.
        # Matching on the visit's reference alone would leave a profile that
        # exists, belongs to this patient, and is invisible on their report.
        refs: tuple[tuple[str, str], ...] = ((ref.type.value, ref.value),)
        if self._links is not None:
            refs = await self._links.aliases_for(
                hospital_id=record.hospital_id,
                ref_type=ref.type.value,
                ref_value=ref.value,
            )
        row = await self._ayush_profiles.current_for_refs(
            hospital_id=record.hospital_id, refs=refs
        )
        return snapshot_of(row)

    async def _prior_records(self, record: CanonicalRecord) -> list[CanonicalRecord]:
        ref = record.patient_ref
        if self._links is None or ref.value is None or ref.type is PatientRefType.GUEST:
            return []
        refs = await self._links.aliases_for(
            hospital_id=record.hospital_id,
            ref_type=ref.type.value,
            ref_value=ref.value,
        )
        rows = await self._intakes.history_for(
            hospital_id=record.hospital_id, refs=refs, limit=self._max_prior_intakes
        )
        prior: list[CanonicalRecord] = []
        for row in rows:
            # This intake is not its own history.
            if row.id == str(record.intake_id):
                continue
            prior.append(
                await self._intakes.load(
                    hospital_id=record.hospital_id, intake_id=row.id
                )
            )
        return prior

    async def build(
        self, *, hospital_id: str, intake_id: str, language: str | None = None
    ) -> ReportBundle:
        """Generate the report and persist it."""
        record = await self.load_record(hospital_id=hospital_id, intake_id=intake_id)
        templates = self._templates.resolve(language or record.language)

        extractions = await self._extractions_for(
            hospital_id=hospital_id, intake_id=intake_id
        )
        interactions = self._interactions_for(record, extractions)
        timeline = await self._timeline_for(record, extractions, templates.language)
        ayush_profile = await self._ayush_profile_for(record)

        report = builder.build(
            record,
            templates=templates,
            extractions=extractions,
            interactions=interactions,
            timeline=timeline,
            ayush_profile=ayush_profile,
            labels=self._labels,
            demo=self._demo,
        )
        text = builder.render_text(report, templates)

        now = self._clock.now()
        stored = await self._reports.upsert(
            report_id=self._ids.new_id("report"),
            hospital_id=hospital_id,
            intake_id=intake_id,
            language=templates.language,
            template_version=report.template_version,
            body=report.model_dump(mode="json"),
            generated_at=now,
            service_date=self._service_date(),
        )
        # Verification lives on the stored row and survives regeneration; the
        # builder is pure and knows nothing about it. Without this line a report
        # read back after sign-off comes out unverified, and the dashboard shows
        # a signed record as a draft — which was the state of it until the
        # end-to-end journey walked the whole sequence and noticed.
        if stored.physician_verified_by is not None:
            report = report.model_copy(
                update={"physician_verified_by": stored.physician_verified_by}
            )
        await self._bus.publish(
            Event(
                name=EventName.REPORT_READY,
                occurred_at=now,
                intake_id=intake_id,
                department_code=record.department_code,
                payload={
                    "language": templates.language,
                    "unresolved_count": len(report.unresolved),
                    "conflict_count": len(report.conflicts),
                    "needs_verification": report.needs_verification,
                },
            )
        )
        return ReportBundle(report=report, text=text)

    def _service_date(self) -> date:
        """The hospital's calendar day.

        "Today's OPD" means today where the hospital is. In IST that differs
        from UTC for five and a half hours every night, which is exactly when an
        evening clinic files its reports under yesterday.
        """
        from zoneinfo import ZoneInfo

        return self._clock.now().astimezone(ZoneInfo(self._timezone)).date()

    async def _extractions_for(
        self, *, hospital_id: str, intake_id: str
    ) -> tuple[DocumentExtraction, ...]:
        """Rebuild extractions from stored rows.

        Reconstruction lives in the repository, because the worker's replay path
        needs the same thing and two row-to-extraction mappers would eventually
        read one column differently.
        """
        return await self._documents.extractions_for_intake(
            hospital_id=hospital_id, intake_id=intake_id
        )

    def _interactions_for(
        self, record: CanonicalRecord, extractions: Sequence[DocumentExtraction]
    ) -> tuple[InteractionFinding, ...]:
        from app.domain.documents.interactions import MedicineEntry, check

        entries: list[MedicineEntry] = []
        for fact in record.facts_in(Section.MEDICATIONS):
            if not fact.is_established:
                continue
            rendered = fact.rendered_value() or fact.original_text or ""
            key = self._ingredients.resolve(rendered)
            if key:
                entries.append(MedicineEntry(display=rendered, ingredient_key=key))
        for extraction in extractions:
            for item in extraction.medicines():
                assert item.medicine is not None
                key = item.medicine.ingredient_key or self._ingredients.resolve(
                    item.medicine.name
                )
                if key:
                    entries.append(
                        MedicineEntry(display=item.medicine.name, ingredient_key=key)
                    )
        return check(entries, self._interactions)

    async def stored(
        self, *, hospital_id: str, intake_id: str, language: str
    ) -> PhysicianReport | None:
        row = await self._reports.get(
            hospital_id=hospital_id, intake_id=intake_id, language=language
        )
        return None if row is None else PhysicianReport.model_validate(row.body)

    # --- verification -------------------------------------------------------

    async def verify(
        self,
        *,
        hospital_id: str,
        intake_id: str,
        physician_id: str,
        field_ids: Sequence[str] | None = None,
        language: str | None = None,
    ) -> ReportBundle:
        """A physician confirms the record, or the fields they name.

        Verification writes **new fact revisions**, one per verified field, each
        recording who verified it. It does not edit the originals: the point of
        an append-only log is that "the physician confirmed this at 10:42" is
        itself a fact with a timestamp.

        Unsettled fields are skipped. There is nothing to confirm about a
        question that was never answered, and marking one verified would turn an
        unresolved field into an established one with a physician's name on it —
        the exact certainty increase the record model exists to prevent.
        """
        record = await self._intakes.load(hospital_id=hospital_id, intake_id=intake_id)
        now = self._clock.now()

        wanted = set(field_ids) if field_ids else None
        if wanted is not None:
            known = {f.field_id for f in record.live_facts()}
            unknown = sorted(wanted - known)
            if unknown:
                raise ValidationError(
                    "cannot verify fields that are not on this record",
                    details={"unknown_fields": unknown},
                )

        revisions: list[Fact] = []
        skipped: list[str] = []
        for fact in record.live_facts():
            if wanted is not None and fact.field_id not in wanted:
                continue
            if not fact.is_answered:
                skipped.append(fact.field_id)
                continue
            if fact.physician_verified:
                continue
            revisions.append(
                fact.verified_by_physician(
                    new_fact_id=self._ids.new_id("fact"),
                    recorded_at=now,
                    physician_id=physician_id,
                )
            )

        await self._intakes.append_facts(
            hospital_id=hospital_id, intake_id=intake_id, facts=revisions
        )
        await self._intakes.mark_seen(
            hospital_id=hospital_id, intake_id=intake_id, actor_id=physician_id, at=now
        )
        await self._audit.write(
            hospital_id=hospital_id,
            occurred_at=now,
            actor_id=physician_id,
            actor_role="physician",
            action="intake.verified",
            entity_type="intake",
            entity_id=intake_id,
            after={
                "verified_count": len(revisions),
                "skipped_unsettled": len(skipped),
            },
            reason="physician verification",
        )

        bundle = await self.build(
            hospital_id=hospital_id, intake_id=intake_id, language=language
        )
        await self._reports.mark_verified(
            hospital_id=hospital_id,
            intake_id=intake_id,
            language=bundle.report.language,
            actor_id=physician_id,
            at=now,
        )
        await self._bus.publish(
            Event(
                name=EventName.REPORT_PHYSICIAN_VERIFIED,
                occurred_at=now,
                intake_id=intake_id,
                actor_id=physician_id,
                payload={"verified_count": len(revisions)},
            )
        )
        logger.info(
            "intake_verified",
            intake_id=intake_id,
            actor_id=physician_id,
            count=len(revisions),
        )
        return bundle.model_copy(
            update={
                "report": bundle.report.model_copy(
                    update={"physician_verified_by": physician_id}
                )
            }
        )

    async def verify_fact(
        self,
        *,
        hospital_id: str,
        intake_id: str,
        fact_id: str,
        physician_id: str,
        action: PhysicianAction,
        value: FactValue | None = None,
        reason: str | None = None,
    ) -> Fact:
        """One fact: accept it, amend it, or reject it — 3/3 §6.

        The per-fact counterpart to `verify`, and the one the dashboard actually
        drives. All three write a **new revision**; none edits what is there. A
        physician correcting a misheard answer must not erase the misheard
        answer, because the proportion of facts they correct is this project's
        extraction-quality metric and a log that rewrites history cannot produce
        one.

        Acting on a superseded revision is a conflict rather than a silent
        success. Two clinicians with the same report open, one amending a value
        the other already changed, is a real sequence in a two-minute
        consultation, and the second one needs to be told rather than have their
        edit land on a fact nobody is looking at.
        """
        record = await self._intakes.load(hospital_id=hospital_id, intake_id=intake_id)
        fact = record.fact(fact_id)
        if fact is None:
            raise NotFoundError(
                f"no fact {fact_id!r} on intake {intake_id}",
                details={"intake_id": intake_id, "fact_id": fact_id},
            )
        if fact not in record.live_facts():
            raise ConflictError(
                "this fact has been superseded; reload the report before acting on it",
                details={"intake_id": intake_id, "fact_id": fact_id},
            )

        now = self._clock.now()
        new_fact_id = self._ids.new_id("fact")
        if action is PhysicianAction.VERIFIED:
            if not fact.is_answered:
                # The same refusal `verify` makes in bulk, made loudly here
                # because this one was a deliberate click on a specific line. A
                # physician's signature on an unresolved field would turn "the
                # patient could not say" into an established finding.
                raise ValidationError(
                    "there is nothing to confirm on a field that was never answered; "
                    "amend it if you know the value",
                    details={"fact_id": fact_id, "status": fact.status.value},
                )
            revision = fact.verified_by_physician(
                new_fact_id=new_fact_id, recorded_at=now, physician_id=physician_id
            )
        elif action is PhysicianAction.AMENDED:
            if value is None:
                raise ValidationError(
                    "an amendment must carry the corrected value",
                    details={"fact_id": fact_id},
                )
            revision = fact.amended_by_physician(
                new_fact_id=new_fact_id,
                recorded_at=now,
                physician_id=physician_id,
                value=value,
                reason=reason,
            )
        else:
            revision = fact.rejected_by_physician(
                new_fact_id=new_fact_id,
                recorded_at=now,
                physician_id=physician_id,
                reason=reason,
            )

        await self._intakes.append_facts(
            hospital_id=hospital_id, intake_id=intake_id, facts=[revision]
        )
        # Actor, before, after and reason — §6. The rendered values are clinical
        # text and this is the one place that is correct: an audit entry that
        # records a correction without recording what was corrected proves
        # nothing. `app/core/logging.py` keeps it out of the log stream; the
        # audit table is not the log stream.
        await self._audit.write(
            hospital_id=hospital_id,
            occurred_at=now,
            actor_id=physician_id,
            actor_role="physician",
            action=f"fact.{action.value}",
            entity_type="clinical_fact",
            entity_id=fact.fact_id,
            before={
                "field_id": fact.field_id,
                "status": fact.status.value,
                "value": fact.rendered_value(),
                "certainty": fact.certainty.value,
            },
            after={
                "fact_id": revision.fact_id,
                "status": revision.status.value,
                "value": revision.rendered_value(),
                "certainty": revision.certainty.value,
            },
            reason=reason,
        )
        await self._bus.publish(
            Event(
                name=EventName.REPORT_PHYSICIAN_VERIFIED,
                occurred_at=now,
                intake_id=intake_id,
                department_code=record.department_code,
                actor_id=physician_id,
                # The field id and the action, never the value. This frame
                # reaches every dashboard subscribed to the department.
                payload={"action": action.value, "field_id": fact.field_id},
            )
        )
        logger.info(
            "fact_reviewed",
            intake_id=intake_id,
            fact_id=fact.fact_id,
            field_id=fact.field_id,
            action=action.value,
            actor_id=physician_id,
        )
        return revision

    async def evidence_for(
        self, *, hospital_id: str, intake_id: str, fact_id: str
    ) -> dict[str, object]:
        """Everything behind one fact, for the evidence panel.

        This endpoint is why every fact carries a `SourceRef`: it turns a line of
        the report into the transcript turn or the region of the scan it came
        from.
        """
        record = await self._intakes.load(hospital_id=hospital_id, intake_id=intake_id)
        fact = record.fact(fact_id)
        if fact is None:
            raise NotFoundError(f"no fact {fact_id!r} on intake {intake_id}")
        return {
            "fact_id": fact.fact_id,
            "field_id": fact.field_id,
            "status": fact.status.value,
            "value": fact.value.model_dump(mode="json") if fact.value else None,
            "original_text": fact.original_text,
            "language": fact.language,
            "certainty": fact.certainty.value,
            "channel": fact.channel.value,
            "confidence": fact.confidence,
            "repaired": fact.repaired,
            "needs_verification": fact.needs_verification,
            "physician_verified": fact.physician_verified,
            "physician_action": (
                fact.physician_action.value
                if fact.physician_action is not None
                else None
            ),
            # Which previous visit this came from, so the panel can link to it
            # (§5) — and whether the patient confirmed it today, which is what
            # decides whether the physician needs to re-ask.
            "carried_forward": (
                fact.carried_forward.model_dump(mode="json")
                if fact.carried_forward is not None
                else None
            ),
            "source": fact.source.model_dump(mode="json"),
            "recorded_at": fact.recorded_at.isoformat(),
            "supersedes": fact.supersedes,
        }


