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
import { statesFor, type FactLike, type FactState } from './factState';

export interface ReportLine {
  text: string;
  fact_ids?: readonly string[];
  field_ids?: readonly string[];
  markers?: readonly { code: string; text: string }[];
  original_text?: string | null;
  original_language?: string | null;
}

export interface ReportSection {
  section: string;
  title: string;
  lines: readonly ReportLine[];
}

export interface Contradiction {
  field_id?: string;
  description?: string;
  claims?: readonly { text: string; source?: string }[];
}

export interface PhysicianReport {
  intake_id: string;
  language: string;
  sections?: readonly ReportSection[];
  unresolved?: readonly ReportLine[];
  conflicts?: readonly Contradiction[];
  interactions?: readonly { text: string; severity: string; source: string }[];
  document_notes?: readonly ReportLine[];
}

interface Props {
  report: PhysicianReport;
  /** Facts by id, for the state of each line. */
  facts: Record<string, FactLike>;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
}

export function ReportView({ report, facts, selectedFactId, onSelectFact }: Props) {
  const sections = report.sections ?? [];
  return (
    <article className="space-y-6" aria-label="Patient report">
      {sections
        .filter((section) => section.lines.length > 0)
        .map((section) => (
          <ReportSectionBlock
            key={section.section}
            section={section}
            facts={facts}
            selectedFactId={selectedFactId}
            onSelectFact={onSelectFact}
          />
        ))}

      {/* Full sections, never a toggle — §12. */}
      <UnresolvedBlock lines={report.unresolved ?? []} facts={facts} />
      <ConflictsBlock conflicts={report.conflicts ?? []} />
    </article>
  );
}

function ReportSectionBlock({
  section,
  facts,
  selectedFactId,
  onSelectFact,
}: {
  section: ReportSection;
  facts: Record<string, FactLike>;
  selectedFactId: string | null;
  onSelectFact: (factId: string) => void;
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
}: {
  line: ReportLine;
  facts: Record<string, FactLike>;
  selected: boolean;
  onSelect: (factId: string) => void;
}) {
  const factId = line.fact_ids?.[0];
  const fact = factId ? facts[factId] : undefined;
  const states = statesFor(line, fact);
  const traceable = Boolean(factId);

  return (
    <li>
      {/* §1 rule 5: every displayed fact is traceable in one click. A line with
          no fact behind it is not clickable rather than clickable-and-inert. */}
      <button
        type="button"
        disabled={!traceable}
        onClick={() => factId && onSelect(factId)}
        data-fact-id={factId}
        data-states={states.join(' ')}
        aria-current={selected ? 'true' : undefined}
        className={`w-full rounded px-2 py-1.5 text-left transition ${
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
      </button>
    </li>
  );
}

function UnresolvedBlock({
  lines,
  facts,
}: {
  lines: readonly ReportLine[];
  facts: Record<string, FactLike>;
}) {
  return (
    <section aria-labelledby="section-unresolved" data-testid="unresolved-section">
      <h3
        id="section-unresolved"
        className="mb-2 text-xs font-semibold uppercase tracking-wide text-uncertain"
      >
        Unresolved
      </h3>
      {lines.length === 0 ? (
        <p className="px-2 text-sm text-ink-muted">Nothing unresolved.</p>
      ) : (
        <ul className="space-y-1">
          {lines.map((line, index) => (
            <FactLine
              key={`unresolved-${index}`}
              line={line}
              facts={facts}
              selected={false}
              onSelect={() => undefined}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function ConflictsBlock({ conflicts }: { conflicts: readonly Contradiction[] }) {
  return (
    <section aria-labelledby="section-conflicts" data-testid="conflicts-section">
      <h3
        id="section-conflicts"
        className="mb-2 text-xs font-semibold uppercase tracking-wide text-conflict"
      >
        Conflicts
      </h3>
      {conflicts.length === 0 ? (
        <p className="px-2 text-sm text-ink-muted">No conflicting accounts.</p>
      ) : (
        <ul className="space-y-2">
          {conflicts.map((conflict, index) => (
            <li
              key={`conflict-${index}`}
              className="rounded border border-conflict/30 bg-conflict-soft p-2"
            >
              <p className="text-sm font-medium text-conflict">
                {conflict.description ?? conflict.field_id}
              </p>
              {/* Both claims side by side, both sources, unresolved — §4.2. The
                  dashboard does not pick a winner; that is the physician's. */}
              <div className="mt-1 grid gap-2 sm:grid-cols-2">
                {(conflict.claims ?? []).map((claim, claimIndex) => (
                  <div
                    key={claimIndex}
                    className="rounded border border-line bg-surface p-2 text-sm"
                  >
                    <p className="text-ink">{claim.text}</p>
                    {claim.source && (
                      <p className="mt-0.5 text-xs text-ink-faint">{claim.source}</p>
                    )}
                  </div>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
