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
import { useT } from '../i18n';

export function MetricsPage() {
  const t = useT();
  const metrics = useCorrectionRate();

  if (metrics.isLoading) return <p className="text-ink-muted">{t('common.loading')}</p>;
  if (metrics.isError || !metrics.data) {
    return (
      <p role="alert" className="text-urgent">
        {t('metrics.error')}
      </p>
    );
  }

  const data = metrics.data;
  const rate = data.correction_rate;

  return (
    <div className="max-w-2xl space-y-4">
      <header>
        <h1 className="text-lg font-semibold text-ink">{t('metrics.title')}</h1>
        <p className="text-sm text-ink-muted">{t('metrics.subtitle')}</p>
      </header>

      <section className="rounded border border-line bg-surface p-4">
        <p className="text-xs uppercase tracking-wide text-ink-faint">
          {t('metrics.correctionRate')}
        </p>
        <p className="mt-1 text-3xl font-semibold tabular-nums text-ink">
          {rate === null || rate === undefined ? (
            <span className="text-xl text-ink-muted">{t('metrics.notMeasurable')}</span>
          ) : (
            `${Math.round(rate * 1000) / 10}%`
          )}
        </p>
        <p className="mt-1 text-sm text-ink-muted">
          {/* The denominator is never dropped. It is what decides whether the
              rate means anything, and quoting a rate without it is how a number
              from four facts ends up on a slide beside one from four thousand. */}
          {t('metrics.breakdown', {
            amended: data.amended,
            rejected: data.rejected,
            reviewed: data.facts_reviewed,
            intakes: data.intakes_reviewed,
          })}
        </p>
      </section>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Counter label={t('metrics.reviewed')} value={data.facts_reviewed} />
        <Counter label={t('metrics.verified')} value={data.verified} />
        <Counter label={t('metrics.amended')} value={data.amended} />
        <Counter label={t('metrics.rejected')} value={data.rejected} />
      </dl>

      <p className="rounded border border-line bg-surface-sunken p-3 text-xs text-ink-muted">
        {t('metrics.note')}
        {(rate === null || rate === undefined) && <> {t('metrics.noteEmpty')}</>}
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
