/**
 * Where the time is going, and what the pharmacy is short of.
 *
 * Two tables, both counted rather than modelled. Nothing on this screen is a
 * forecast, a prediction or a score, and the page says so out loud — an
 * operations view that quietly implies otherwise is how a hospital ends up
 * planning against a number nobody measured.
 *
 * **Sorted by longest wait, not by volume.** The busiest department is not the
 * problem; the department with somebody in it who has been there ninety minutes
 * is. The backend sorts it that way and this screen does not re-sort.
 *
 * Admin-only, and the backend enforces that. The route guard here keeps a
 * physician from being shown a screen that would only refuse them.
 */
import { useOperations, useStockAlerts } from '../api/queries';
import type { DepartmentLoad, StockAlert } from '../api/types';
import { useT, type Translate } from '../i18n';
import { humanise, isoDate, timeOfDay } from '../lib/format';
import { StockStateChip } from './chips';

export function OperationsPage() {
  const t = useT();
  const operations = useOperations();
  const stock = useStockAlerts();

  return (
    <div className="max-w-4xl space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-ink">{t('ops.title')}</h1>
        <p className="text-sm text-ink-muted">{t('ops.subtitle')}</p>
      </header>

      <section className="surface-card p-5" aria-label={t('ops.load')} data-testid="department-load">
        <h2 className="text-sm font-semibold text-ink">{t('ops.load')}</h2>
        <p className="mt-0.5 text-xs text-ink-muted">{t('ops.loadNote')}</p>

        {operations.isError && (
          <p role="alert" className="mt-3 text-xs font-semibold text-alert">
            {t('ops.loadError')}
          </p>
        )}

        {operations.isLoading && (
          <p className="mt-3 text-sm text-ink-muted">{t('common.loading')}</p>
        )}

        {/* "Nothing needs attention" is a claim about the hospital. It is only
            made once the answer has arrived — shown while a request is still in
            flight it is a claim nobody has checked. */}
        {!operations.isLoading &&
          !operations.isError &&
          (operations.data?.departments ?? []).length === 0 && (
            <p className="mt-3 text-sm text-ink-muted">{t('ops.nobodyWaiting')}</p>
          )}

        {(operations.data?.departments ?? []).length > 0 && (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-[0.08em] text-ink-faint">
                <th className="py-1.5 font-semibold">{t('ops.department')}</th>
                <th className="py-1.5 font-semibold tabular-nums">{t('ops.waiting')}</th>
                <th className="py-1.5 font-semibold tabular-nums">{t('ops.flagged')}</th>
                <th className="py-1.5 font-semibold tabular-nums">{t('ops.longest')}</th>
                <th className="py-1.5 font-semibold tabular-nums">{t('ops.unfilled')}</th>
              </tr>
            </thead>
            <tbody>
              {(operations.data?.departments ?? []).map((load) => (
                <LoadRow key={load.department_code} load={load} t={t} />
              ))}
            </tbody>
          </table>
        )}

        {operations.data?.generated_at && (
          <p className="mt-3 text-[11px] text-ink-faint">
            {t('ops.asOf', { time: timeOfDay(operations.data.generated_at) })}
          </p>
        )}
      </section>

      <section className="surface-card p-5" aria-label={t('stock.title')} data-testid="stock-alerts">
        <h2 className="text-sm font-semibold text-ink">{t('stock.title')}</h2>
        <p className="mt-0.5 text-xs text-ink-muted">{t('stock.subtitle')}</p>

        {stock.isError && (
          <p role="alert" className="mt-3 text-xs font-semibold text-alert">
            {t('stock.loadError')}
          </p>
        )}

        {stock.isLoading && (
          <p className="mt-3 text-sm text-ink-muted">{t('common.loading')}</p>
        )}

        {!stock.isLoading && !stock.isError && (stock.data?.alerts ?? []).length === 0 && (
          <p className="mt-3 text-sm text-ink-muted">{t('stock.nothingToAct')}</p>
        )}

        {(stock.data?.alerts ?? []).length > 0 && (
          <ul className="mt-3 divide-y divide-line">
            {(stock.data?.alerts ?? []).map((alert) => (
              <StockRow key={alert.code} alert={alert} t={t} />
            ))}
          </ul>
        )}

        {/* The one thing this list cannot tell anyone, said rather than left to
            be inferred: a medicine with no row is not a medicine with none in
            stock. */}
        <p className="mt-3 rounded border border-line bg-surface-sunken p-3 text-[11px] text-ink-muted">
          {t('stock.unknownNote')}
        </p>
      </section>
    </div>
  );
}

function LoadRow({ load, t }: { load: DepartmentLoad; t: Translate }) {
  return (
    <tr className="border-b border-line/60 last:border-0" data-department={load.department_code}>
      <td className="py-2 font-medium capitalize text-ink">{humanise(load.department_code)}</td>
      <td className="py-2 tabular-nums text-ink">{load.waiting}</td>
      <td className={`py-2 tabular-nums ${load.flagged > 0 ? 'font-semibold text-urgent' : 'text-ink-muted'}`}>
        {load.flagged}
      </td>
      <td className="py-2 tabular-nums text-ink">
        {t('ops.minutes', { minutes: load.longest_wait_minutes })}
      </td>
      <td className={`py-2 tabular-nums ${load.unfilled_orders > 0 ? 'font-semibold text-uncertain' : 'text-ink-muted'}`}>
        {load.unfilled_orders}
      </td>
    </tr>
  );
}

function StockRow({ alert, t }: { alert: StockAlert; t: Translate }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5" data-stock-code={alert.code}>
      <span className="font-medium text-ink">{alert.display}</span>
      <StockStateChip state={alert.state} />
      <span className="text-xs tabular-nums text-ink-muted">
        {t('stock.onHand', { onHand: alert.on_hand, reorder: alert.reorder_level })}
      </span>
      {alert.expires_on && (
        <span className="ml-auto text-xs tabular-nums text-ink-muted">
          {t('stock.expires', { date: isoDate(alert.expires_on) })}
        </span>
      )}
    </li>
  );
}
