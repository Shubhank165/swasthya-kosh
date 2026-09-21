/**
 * The patient report — 3/3 §4.2, the main event.
 *
 * Section order is fixed by the spec and is not a preference:
 * chief complaint first because it is what the consultation is about, and
 * **Unresolved and Conflicts last as full sections rather than a collapsed
 * disclosure**. Hiding the gaps to make the document look tidy would defeat the
 * thing this system is for — the honesty is the product.
 *
 * Nothing here computes. Coverage, red flags, contradictions and every rendered
 * line arrive from the backend already decided (§1 rule 1, §12). What this file
 * decides is *typography*: which of the things the backend sent a physician
 * reads first, and which sit quietly beneath. A report where the chief complaint
 * and "prior investigations" are set in the same 12px weight is one a doctor has
 * to parse rather than read, which is the complaint this rewrite answers.
 */
import { StateChip } from '../components/StateChip';
import { useT, type Translate } from '../i18n';
import type {
  Contradiction,
  ConflictSide,
  InteractionLine,
  PhysicianReport,
  RedFlagLine,
  ReportLine,
  ReportSection,
  TimelineEntry,
  TimelineSnapshot,
} from '../api/types';
import { isoDate } from '../lib/format';
import { statesFor, type FactLike, type FactState } from './factState';

export type { PhysicianReport, ReportLine, ReportSection, Contradiction };

export type ReportTab = 'complaint' | 'ayurveda' | 'meds' | 'labs' | 'discrepancies' | 'all';

interface Props {
  report: PhysicianReport;
  /** Facts by id, for the state of each line. */
  facts: Record<string, FactLike>;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
  /** Rendered beside a line when the reader may act on it — §6. */
  renderActions?: (factId: string) => React.ReactNode;
  activeTab?: ReportTab;
}

/** The chief complaint is what the consultation is about, so it is set larger. */
const LEAD_SECTION = 'chief_complaint';

export function ReportView({
  report,
  facts,
  selectedFactId,
  onSelectFact,
  renderActions,
  activeTab = 'all',
}: Props) {
  const t = useT();
  const label = t('report.aria');
  const sections = report.sections ?? [];
  const labelFor = (fieldId: string) =>
    report.field_labels?.[fieldId] ?? fieldId.replace(/_/g, ' ');

  // Filter sections by activeTab
  const filteredSections = sections.filter((s) => {
    if (activeTab === 'all') return true;
    if (activeTab === 'complaint') {
      return (
        s.section === 'chief_complaint' ||
        s.section === 'hpi' ||
        s.section === 'red_flag_screen' ||
        s.section === 'review_of_systems'
      );
    }
    if (activeTab === 'ayurveda') {
      return s.section === 'ayurveda';
    }
    if (activeTab === 'meds') {
      return s.section === 'medications' || s.section === 'allergies';
    }
    if (activeTab === 'labs') {
      return (
        s.section === 'investigations' ||
        s.section === 'past_medical' ||
        s.section === 'past_surgical' ||
        s.section === 'family_history' ||
        s.section === 'personal_history'
      );
    }
    if (activeTab === 'discrepancies') {
      return false; // Discrepancies has Unresolved, Conflicts & DocumentNotes
    }
    return true;
  });

  const showAyurvedaEmptyNotice =
    activeTab === 'ayurveda' &&
    (filteredSections.length === 0 ||
      filteredSections.every((s) => !s.lines || s.lines.length === 0));

  return (
    <article className="space-y-6" aria-label={label}>
      {/* Alerts render on every tab. A red flag a physician cannot see because
          they are looking at the Ayurveda tab is a red flag that did not fire —
          the point of the block is that it is impossible to miss. */}
      <AlertsBlock alerts={report.alerts ?? []} t={t} />

      {/* Render matching sections */}
      {filteredSections.map((section) => (
        <ReportSectionBlock
          key={section.section}
          section={section}
          lead={section.section === LEAD_SECTION}
          facts={facts}
          selectedFactId={selectedFactId}
          onSelectFact={onSelectFact}
          renderActions={renderActions}
          t={t}
        />
      ))}

      {showAyurvedaEmptyNotice && (
        <div className="surface-card p-6 text-center text-ink-muted">
          <p className="font-medium text-sm text-ink">No Specific Ayurvedic Assessment Reported</p>
          <p className="mt-1 text-xs">
            Patient did not report Dosha-specific aggravation or prior Ayurvedic treatment during kiosk intake.
          </p>
        </div>
      )}

      {/* Interactions on meds or all */}
      {(activeTab === 'all' || activeTab === 'meds') && (
        <InteractionsBlock interactions={report.interactions ?? []} t={t} />
      )}

      {/* History and Timeline on labs or all */}
      {(activeTab === 'all' || activeTab === 'labs') && (
        <>
          <HistoryBlock history={report.history ?? null} t={t} />
          <TimelineBlock entries={report.document_timeline ?? []} t={t} />
        </>
      )}

      {/* Notes are supporting material and stay on their tab. */}
      {(activeTab === 'all' || activeTab === 'discrepancies') && (
        <DocumentNotesBlock
          lines={report.document_notes ?? []}
          facts={facts}
          selectedFactId={selectedFactId}
          onSelectFact={onSelectFact}
          t={t}
        />
      )}

      {/* Conflicts and unresolved are NOT tab-scoped, and must not become so.
          3/3 §12: they are full sections, never behind a toggle — and a tab is
          a toggle. A physician on the default tab would otherwise read a report
          that looks complete while three facts went unanswered and seven
          disagree, with nothing on screen saying so. */}
      <ConflictsBlock
        conflicts={report.conflicts ?? []}
        labelFor={labelFor}
        selectedFactId={selectedFactId}
        onSelectFact={onSelectFact}
      />
      <UnresolvedBlock
        lines={report.unresolved ?? []}
        facts={facts}
        selectedFactId={selectedFactId}
        onSelectFact={onSelectFact}
        renderActions={renderActions}
      />
    </article>
  );
}

/**
 * One section heading. Small caps and muted, deliberately — the heading is
 * furniture and the lines under it are the document.
 */
function SectionHeading({
  id,
  tone = 'muted',
  children,
}: {
  id: string;
  tone?: 'muted' | 'uncertain' | 'conflict' | 'urgent';
  children: React.ReactNode;
}) {
  const colour = {
    muted: 'text-ink-muted border-line',
    uncertain: 'text-uncertain border-uncertain/30',
    conflict: 'text-conflict border-conflict/30',
    urgent: 'text-urgent border-urgent/40',
  }[tone];
  return (
    <h3
      id={id}
      className={`mb-2 border-b pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] ${colour}`}
    >
      {children}
    </h3>
  );
}

function ReportSectionBlock({
  section,
  lead,
  facts,
  selectedFactId,
  onSelectFact,
  renderActions,
  t,
}: {
  section: ReportSection;
  lead: boolean;
  facts: Record<string, FactLike>;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
  renderActions?: (factId: string) => React.ReactNode;
  t: Translate;
}) {
  if (section.lines.length === 0) {
    return (
      <section aria-labelledby={`section-${section.section}`} data-empty="true">
        <SectionHeading id={`section-${section.section}`}>{section.title}</SectionHeading>
        <p className="text-ink-soft">{t('report.sectionEmpty')}</p>
      </section>
    );
  }
  return (
    <section aria-labelledby={`section-${section.section}`}>
      <SectionHeading id={`section-${section.section}`}>{section.title}</SectionHeading>
      <ul className="space-y-0.5">
        {section.lines.map((line, index) => (
          <FactLine
            key={`${section.section}-${index}`}
            line={line}
            lead={lead}
            facts={facts}
            selected={!!line.fact_ids?.some((id) => id === selectedFactId)}
            onSelect={onSelectFact}
            renderActions={renderActions}
          />
        ))}
      </ul>
    </section>
  );
}

export function FactLine({
  line,
  lead = false,
  facts,
  selected,
  onSelect,
  renderActions,
}: {
  line: ReportLine;
  lead?: boolean;
  facts: Record<string, FactLike>;
  selected: boolean;
  onSelect: (factId: string) => void;
  renderActions?: (factId: string) => React.ReactNode;
}) {
  const factId = line.fact_ids?.[0];
  const fact = factId ? facts[factId] : undefined;
  const states = statesFor(line, fact);
  const traceable = Boolean(factId);
  // The builder states the halves; this screen never splits the string itself.
  const split = line.label != null && line.value != null;

  return (
    <li className="group flex items-start gap-2">
      {/* §1 rule 5: every displayed fact is traceable in one click. A line with
          no fact behind it is not clickable rather than clickable-and-inert. */}
      <button
        type="button"
        disabled={!traceable}
        onClick={() => factId && onSelect(factId)}
        data-fact-id={factId}
        data-states={states.join(' ')}
        aria-current={selected ? 'true' : undefined}
        className={`flex-1 rounded px-2 py-1.5 text-left transition ${
          selected ? 'bg-accent-soft ring-1 ring-accent/40' : 'hover:bg-surface-sunken'
        } ${traceable ? '' : 'cursor-default'}`}
      >
        {split ? (
          // A label column and a value column, rather than one run of text that
          // happens to contain a colon. The label is the quieter half: a
          // physician scans for the value.
          <span className="flex flex-col gap-x-3 sm:flex-row sm:items-baseline">
            <span className="shrink-0 text-sm text-ink-muted sm:w-44">{line.label}</span>
            <span
              className={
                lead
                  ? 'font-semibold text-ink text-[17px] leading-snug'
                  : 'text-ink'
              }
            >
              {line.value}
            </span>
          </span>
        ) : (
          <span className={lead ? 'font-semibold text-ink text-[17px]' : 'text-ink'}>
            {line.text}
          </span>
        )}

        {states.some((s) => s !== 'confirmed') && (
          <span className="mt-1 inline-flex flex-wrap gap-1 align-middle">
            {states
              .filter((s): s is FactState => s !== 'confirmed')
              .map((state) => (
                <StateChip key={state} state={state} />
              ))}
          </span>
        )}
        {/* The patient's own words, verbatim and never translated in place
            (§9). A translation, where there is one, goes beneath — not over. */}
        {line.original_text && (
          <span
            lang={line.original_language ?? undefined}
            className="mt-1 block border-l-2 border-line pl-2 text-sm text-ink-muted"
          >
            {line.original_text}
          </span>
        )}
        {/* Every marker the backend attached, in its own words. Dropping one
            because the chip above already implies it would be this screen
            deciding which qualifiers a physician needs — so they are all here,
            as chips rather than a semicolon-joined string, which is what made
            the provenance signals read like a serialised array. */}
        {(line.markers?.length ?? 0) > 0 && (
          <span className="mt-1.5 flex flex-wrap gap-1">
            {line.markers!.map((marker) => (
              <span
                key={marker.code}
                data-marker={marker.code}
                className="inline-flex rounded border border-line bg-surface-sunken px-1.5 py-0.5 text-xs text-ink-muted"
              >
                {marker.text}
              </span>
            ))}
          </span>
        )}
      </button>
      {factId && renderActions?.(factId)}
    </li>
  );
}

function AlertsBlock({ alerts, t }: { alerts: readonly RedFlagLine[]; t: Translate }) {
  if (alerts.length === 0) return null;
  return (
    <section aria-labelledby="section-alerts" data-testid="report-alerts">
      <SectionHeading id="section-alerts" tone="urgent">
        {t('report.alerts')}
      </SectionHeading>
      <ul className="space-y-2">
        {alerts.map((alert) => (
          <li
            key={alert.rule_id}
            data-rule-id={alert.rule_id}
            data-severity={alert.severity}
            className="rounded border border-urgent/40 bg-urgent-soft p-2.5"
          >
            {/* The label the backend wrote, or the rule id when it wrote none.
                This screen does not invent a phrase for a criterion. */}
            <p className="font-semibold text-urgent">
              {alert.label ?? alert.rule_id.replace(/_/g, ' ')}
            </p>
            {(alert.criteria_met?.length ?? 0) > 0 && (
              <p className="mt-0.5 text-sm text-urgent/90">
                {alert.criteria_met!.join(' · ')}
              </p>
            )}
            <p className="mt-1 text-xs text-ink-muted">
              {alert.acknowledged_by
                ? t('report.alertAcknowledged', { actor: alert.acknowledged_by })
                : t('report.alertUnacknowledged')}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function InteractionsBlock({
  interactions,
  t,
}: {
  interactions: readonly InteractionLine[];
  t: Translate;
}) {
  if (interactions.length === 0) return null;
  return (
    <section aria-labelledby="section-interactions" data-testid="report-interactions">
      <SectionHeading id="section-interactions" tone="uncertain">
        {t('report.interactions')}
      </SectionHeading>
      <ul className="space-y-2">
        {interactions.map((interaction, index) => (
          <li
            key={`${interaction.source}-${index}`}
            data-severity={interaction.severity}
            className="rounded border border-uncertain/30 bg-uncertain-soft p-2.5"
          >
            {/* A request to look, never a recommendation — the backend's own
                wording carries that and is printed unaltered. */}
            <p className="text-ink">{interaction.text}</p>
            <p className="mt-1 text-xs text-ink-muted">
              {t('report.interactionSource', { source: interaction.source })}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function HistoryBlock({
  history,
  t,
}: {
  history: TimelineSnapshot | null;
  t: Translate;
}) {
  // A missing `history` field is an older report body, built before this
  // section existed. Nothing is coming for it, so there is nothing to say.
  if (history === null) return null;

  const events = history.events ?? [];
  // Three states, three different sentences. A reader cannot tell them apart
  // from the list alone, and "not built yet" is not "nothing on record".
  const note =
    history.status === 'pending'
      ? t('report.historyPending')
      : events.length === 0
        ? t('report.historyNone')
        : history.status === 'filtered'
          ? t('report.historyFiltered', { omitted: history.omitted_count ?? 0 })
          : t('report.historyUnfiltered');

  return (
    <section aria-labelledby="section-history" data-testid="history-timeline">
      <SectionHeading id="section-history">{t('report.history')}</SectionHeading>
      {events.length > 0 && (
        <ol className="space-y-1">
          {events.map((event) => (
            <li
              key={`${event.event_date}-${event.candidate_id ?? event.label}`}
              data-event-kind={event.kind}
              className="flex items-baseline gap-3 px-2 py-1"
            >
              <span className="w-28 shrink-0 text-sm tabular-nums text-ink-muted">
                {isoDate(event.event_date)}
              </span>
              <span className="text-ink">{event.label}</span>
              {/* Why it was kept, when a model made that call. Named rather
                  than scored: "0.9" tells a physician nothing they can check. */}
              {event.relevance_reason && (
                <span className="text-xs text-ink-faint">
                  {event.relevance_reason}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
      {/* Always printed, never conditional on the list being short. A filtered
          timeline that does not say it is filtered reads as a complete
          history and is not. */}
      <p
        data-testid="history-status"
        data-status={history.status}
        className={`mt-1.5 px-2 text-xs ${
          history.status === 'pending' ? 'text-uncertain' : 'text-ink-faint'
        }`}
      >
        {note}
      </p>
    </section>
  );
}

function TimelineBlock({
  entries,
  t,
}: {
  entries: readonly TimelineEntry[];
  t: Translate;
}) {
  if (entries.length === 0) return null;
  return (
    <section aria-labelledby="section-document-timeline" data-testid="document-timeline">
      <SectionHeading id="section-document-timeline">
        {t('report.documentTimeline')}
      </SectionHeading>
      <ol className="space-y-1">
        {entries.map((entry) => (
          <li
            key={entry.document_id}
            data-document-id={entry.document_id}
            data-dated={String(entry.dated)}
            className="flex items-baseline gap-3 px-2 py-1"
          >
            {/* An undated document says so in the date column rather than
                showing a blank one. It cannot be placed, and that is the
                finding. */}
            <span
              className={`w-28 shrink-0 text-sm tabular-nums ${
                entry.dated ? 'text-ink-muted' : 'text-uncertain'
              }`}
            >
              {entry.dated ? isoDate(entry.document_date) : t('report.documentUndated')}
            </span>
            <span className="text-ink">{entry.text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function DocumentNotesBlock({
  lines,
  facts,
  selectedFactId,
  onSelectFact,
  t,
}: {
  lines: readonly ReportLine[];
  facts: Record<string, FactLike>;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
  t: Translate;
}) {
  if (lines.length === 0) return null;
  return (
    <section aria-labelledby="section-document-notes" data-testid="document-notes">
      <SectionHeading id="section-document-notes">
        {t('report.documentNotes')}
      </SectionHeading>
      <ul className="space-y-0.5">
        {lines.map((line, index) => (
          <FactLine
            key={`document-note-${index}`}
            line={line}
            facts={facts}
            selected={!!line.fact_ids?.some((id) => id === selectedFactId)}
            onSelect={onSelectFact}
          />
        ))}
      </ul>
    </section>
  );
}

function UnresolvedBlock({
  lines,
  facts,
  selectedFactId,
  onSelectFact,
  renderActions,
}: {
  lines: readonly ReportLine[];
  facts: Record<string, FactLike>;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
  renderActions?: (factId: string) => React.ReactNode;
}) {
  const t = useT();
  return (
    <section aria-labelledby="section-unresolved" data-testid="unresolved-section">
      <SectionHeading id="section-unresolved" tone="uncertain">
        {t('report.unresolved')}
      </SectionHeading>
      {lines.length === 0 ? (
        <p className="px-2 text-sm text-ink-muted">{t('report.nothingUnresolved')}</p>
      ) : (
        <ul className="space-y-0.5">
          {lines.map((line, index) => (
            <FactLine
              key={`unresolved-${index}`}
              line={line}
              facts={facts}
              selected={!!line.fact_ids?.some((id) => id === selectedFactId)}
              onSelect={onSelectFact}
              renderActions={renderActions}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function ConflictsBlock({
  conflicts,
  labelFor,
  selectedFactId,
  onSelectFact,
}: {
  conflicts: readonly Contradiction[];
  labelFor: (fieldId: string) => string;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
}) {
  const t = useT();
  return (
    <section aria-labelledby="section-conflicts" data-testid="conflicts-section">
      <SectionHeading id="section-conflicts" tone="conflict">
        {t('report.conflicts')}
      </SectionHeading>
      {conflicts.length === 0 ? (
        <p className="px-2 text-sm text-ink-muted">{t('report.noConflicts')}</p>
      ) : (
        <ul className="space-y-2">
          {conflicts.map((conflict) => (
            <li
              key={`${conflict.field_id}-${conflict.kind}`}
              className="rounded border border-conflict/30 bg-conflict-soft p-2"
              data-field-id={conflict.field_id}
            >
              {/* The backend's label for the field, not a de-underscored
                  database identifier used as a clinical heading. */}
              <p className="text-sm font-semibold text-conflict">
                {labelFor(conflict.field_id)}
              </p>
              {/* Both claims side by side, both sources, unresolved — §4.2. The
                  dashboard does not pick a winner; the backend does not either,
                  and `resolution` is always "physician verification required". */}
              <div className="mt-1 grid gap-2 sm:grid-cols-2">
                <ClaimCard
                  heading={t('report.reportedToday')}
                  side={conflict.reported_today ?? null}
                  selectedFactId={selectedFactId}
                  onSelectFact={onSelectFact}
                  t={t}
                />
                <ClaimCard
                  heading={t('report.onRecord')}
                  side={conflict.from_record}
                  selectedFactId={selectedFactId}
                  onSelectFact={onSelectFact}
                  t={t}
                />
              </div>
              <p className="mt-1 text-xs text-conflict">{conflict.resolution}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ClaimCard({
  heading,
  side,
  selectedFactId,
  onSelectFact,
  t,
}: {
  heading: string;
  side: ConflictSide | null;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
  t: Translate;
}) {
  if (side === null) {
    // A conflict can have only one side — a medicine on the prescription that
    // the patient did not mention. Saying so is more useful than hiding the
    // half that exists, and much more useful than implying the patient denied
    // it, which they did not.
    return (
      <div className="rounded border border-dashed border-line bg-surface p-2 text-sm">
        <p className="text-xs font-medium text-ink-muted">{heading}</p>
        <p className="mt-0.5 text-ink-muted">{t('report.notMentioned')}</p>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onSelectFact(side.fact_id)}
      aria-current={selectedFactId === side.fact_id ? 'true' : undefined}
      data-fact-id={side.fact_id}
      className={`rounded border bg-surface p-2 text-left text-sm ${
        selectedFactId === side.fact_id
          ? 'border-accent ring-1 ring-accent/40'
          : 'border-line hover:bg-surface-sunken'
      }`}
    >
      <p className="text-xs font-medium text-ink-muted">{heading}</p>
      <p className="text-ink">{side.statement}</p>
      {side.original_text && (
        <p className="mt-0.5 border-l-2 border-line pl-2 text-ink-muted">
          {side.original_text}
        </p>
      )}
      <p className="mt-0.5 text-xs text-ink-faint">{side.source_label}</p>
    </button>
  );
}
