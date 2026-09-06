/**
 * The correction rate — 3/3 §6, §B3.
 *
 * A small admin view, and it is worth having for a reason beyond the slide:
 * **the proportion of facts a physician amends is this project's extraction
 * quality metric.** It replaces the figures the shelved evaluation harness used
 * to produce — those measured question selection, which now runs on the Jetson,
 * so they no longer describe anything this backend does.
 *
 * The screen says out loud what the number is over. A correction rate quoted
 * without its denominator is not a measurement, and a rate computed from four
 * reviewed facts is not evidence of anything.
 */
import { useCorrectionRate } from '../api/queries';

export function MetricsPage() {
  const metrics = useCorrectionRate();

  if (metrics.isLoading) return <p className="text-ink-muted">Loading…</p>;
  if (metrics.isError || !metrics.data) {
    return (
      <p role="alert" className="text-urgent">
        These counters could not be loaded.
      </p>
    );
  }

  const data = metrics.data;
  const rate = data.correction_rate;

  return (
    <div className="max-w-2xl space-y-4">
      <header>
        <h1 className="text-lg font-semibold text-ink">Extraction quality</h1>
        <p className="text-sm text-ink-muted">
          How often a physician had to correct what the pipeline recorded.
        </p>
      </header>

      <section className="rounded border border-line bg-surface p-4">
        <p className="text-xs uppercase tracking-wide text-ink-faint">
          Correction rate
        </p>
        <p className="mt-1 text-3xl font-semibold tabular-nums text-ink">
          {rate === null || rate === undefined ? (
            <span className="text-xl text-ink-muted">Not yet measurable</span>
          ) : (
            `${Math.round(rate * 1000) / 10}%`
          )}
        </p>
        <p className="mt-1 text-sm text-ink-muted">
          {/* Denominator first. It is what decides whether the rate means
              anything, and quoting a rate without it is how a number from four
              facts ends up on a slide beside one from four thousand. */}
          {data.amended} amended and {data.rejected} rejected, out of{' '}
          <strong className="text-ink">{data.facts_reviewed}</strong> facts a
          physician reviewed across {data.intakes_reviewed} intake
          {data.intakes_reviewed === 1 ? '' : 's'}.
        </p>
      </section>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Counter label="Reviewed" value={data.facts_reviewed} />
        <Counter label="Confirmed as recorded" value={data.verified} />
        <Counter label="Amended" value={data.amended} />
        <Counter label="Rejected" value={data.rejected} />
      </dl>

      <p className="rounded border border-line bg-surface-sunken p-3 text-xs text-ink-muted">
        The denominator is facts a physician actually looked at, not every fact
        stored. A field nobody reviewed says nothing about extraction quality,
        and counting it would let this number be improved by ingesting more
        intakes rather than by extracting better. A field acted on twice counts
        once, with the latest action winning.
        {(rate === null || rate === undefined) && (
          <>
            {' '}
            Until it has data behind it, this figure — and the ones the retired
            evaluation harness produced — should not appear on a slide.
          </>
        )}
      </p>
    </div>
  );
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-line bg-surface p-3">
      <dt className="text-xs uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums text-ink">{value}</dd>
    </div>
  );
}
