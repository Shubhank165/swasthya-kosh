/**
 * The patient report — 3/3 §4.2, the main event.
 *
 * Section order is fixed by the problem statement and is not a preference:
 * chief complaint first because it is what the consultation is about, and
 * **Unresolved and Conflicts last as full sections rather than a collapsed
 * disclosure**. Hiding the gaps to make the document look tidy would defeat the
 * thing this system is for — the honesty is the product.
 *
 * Nothing here computes. Coverage, red flags, contradictions and every rendered
 * line arrive from the backend already decided (§1 rule 1, §12).
 */
import { StateChip } from '../components/StateChip';
import { useT, type Translate } from '../i18n';
import type {
  Contradiction,
  ConflictSide,
  PhysicianReport,
  ReportLine,
  ReportSection,
} from '../api/types';
import { statesFor, type FactLike, type FactState } from './factState';

export type { PhysicianReport, ReportLine, ReportSection, Contradiction };

interface Props {
  report: PhysicianReport;
  /** Facts by id, for the state of each line. */
  facts: Record<string, FactLike>;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
  /** Rendered beside a line when the reader may act on it — §6. */
  renderActions?: (factId: string) => React.ReactNode;
}

export function ReportView({
  report,
  facts,
  selectedFactId,
  onSelectFact,
  renderActions,
}: Props) {
  const t = useT();
  const label = t('report.aria');
  const sections = report.sections ?? [];
  return (
    <article className="space-y-6" aria-label={label}>
      {sections
        .filter((section) => section.lines.length > 0)
        .map((section) => (
          <ReportSectionBlock
            key={section.section}
            section={section}
            facts={facts}
            selectedFactId={selectedFactId}
            onSelectFact={onSelectFact}
            renderActions={renderActions}
          />
        ))}

      {/* Full sections, never a toggle — §12. */}
      <UnresolvedBlock
        lines={report.unresolved ?? []}
        facts={facts}
        selectedFactId={selectedFactId}
        onSelectFact={onSelectFact}
        renderActions={renderActions}
      />
      <ConflictsBlock
        conflicts={report.conflicts ?? []}
        selectedFactId={selectedFactId}
        onSelectFact={onSelectFact}
      />
    </article>
  );
}

function ReportSectionBlock({
  section,
  facts,
  selectedFactId,
  onSelectFact,
  renderActions,
}: {
  section: ReportSection;
  facts: Record<string, FactLike>;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
  renderActions?: (factId: string) => React.ReactNode;
}) {
  return (
    <section aria-labelledby={`section-${section.section}`}>
      <h3
        id={`section-${section.section}`}
        className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted"
      >
        {section.title}
      </h3>
      <ul className="space-y-1">
        {section.lines.map((line, index) => (
          <FactLine
            key={`${section.section}-${index}`}
            line={line}
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
  facts,
  selected,
  onSelect,
  renderActions,
}: {
  line: ReportLine;
  facts: Record<string, FactLike>;
  selected: boolean;
  onSelect: (factId: string) => void;
  renderActions?: (factId: string) => React.ReactNode;
}) {
  const factId = line.fact_ids?.[0];
  const fact = factId ? facts[factId] : undefined;
  const states = statesFor(line, fact);
  const traceable = Boolean(factId);

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
        <span className="text-ink">{line.text}</span>
        {states.some((s) => s !== 'confirmed') && (
          <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
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
            deciding which qualifiers a physician needs. */}
        {(line.markers?.length ?? 0) > 0 && (
          <span className="mt-1 block text-xs text-ink-faint">
            {line.markers!.map((marker) => marker.text).join('; ')}
          </span>
        )}
      </button>
      {factId && renderActions?.(factId)}
    </li>
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
      <h3
        id="section-unresolved"
        className="mb-2 text-xs font-semibold uppercase tracking-wide text-uncertain"
      >
        {t('report.unresolved')}
      </h3>
      {lines.length === 0 ? (
        <p className="px-2 text-sm text-ink-muted">{t('report.nothingUnresolved')}</p>
      ) : (
        <ul className="space-y-1">
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
  selectedFactId,
  onSelectFact,
}: {
  conflicts: readonly Contradiction[];
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
}) {
  const t = useT();
  return (
    <section aria-labelledby="section-conflicts" data-testid="conflicts-section">
      <h3
        id="section-conflicts"
        className="mb-2 text-xs font-semibold uppercase tracking-wide text-conflict"
      >
        {t('report.conflicts')}
      </h3>
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
              <p className="text-sm font-medium text-conflict">
                {conflict.field_id.replace(/_/g, ' ')}
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
