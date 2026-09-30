/**
 * The pharmacy counter — what is short, what is expiring, what has run out.
 *
 * **Deliberately standalone.** The inventory is not a view onto the clinical
 * record and this role holds no access to one: a chemist is refused the
 * worklist, the report, the documents and the evidence. Dispensing against a
 * named prescription would be useful and is a later decision with its own
 * privacy argument; until somebody makes it, this screen is a shelf.
 *
 * Forecasting — how much to order, and the setting that trades money against
 * never being out — lands here next. Today this is the stock list, moved off
 * the admin operations page where a pharmacist could not reach it.
 */
import { useStockAlerts } from '../api/queries';
import type { StockAlert } from '../api/types';
import { StockStateChip } from '../coordination/chips';
import { useT, type Translate } from '../i18n';
import { isoDate, timeOfDay } from '../lib/format';

export function PharmacyPage() {
  const t = useT();
  const stock = useStockAlerts();
  const alerts = stock.data?.alerts ?? [];

  const outOfStock = alerts.filter((a) => a.state === 'out');
  const expired = alerts.filter((a) => a.state === 'expired');

  return (
    <div className="max-w-4xl space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-ink">{t('pharmacy.title')}</h1>
        <p className="text-sm text-ink-muted">{t('pharmacy.subtitle')}</p>
      </header>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Counter label={t('pharmacy.needsAttention')} value={alerts.length} />
        <Counter label={t('stock.state.out')} value={outOfStock.length} urgent={outOfStock.length > 0} />
        <Counter label={t('stock.state.expired')} value={expired.length} urgent={expired.length > 0} />
      </dl>

      <section className="surface-card p-5" aria-label={t('pharmacy.title')} data-testid="pharmacy-stock">
        <h2 className="text-sm font-semibold text-ink">{t('stock.title')}</h2>
        <p className="mt-0.5 text-xs text-ink-muted">{t('stock.subtitle')}</p>

        {stock.isLoading && <p className="mt-3 text-sm text-ink-muted">{t('common.loading')}</p>}

        {stock.isError && (
          <p role="alert" className="mt-3 text-xs font-semibold text-alert">
            {t('stock.loadError')}
          </p>
        )}

        {!stock.isLoading && !stock.isError && alerts.length === 0 && (
          <p className="mt-3 text-sm text-ink-muted">{t('stock.nothingToAct')}</p>
        )}

        {alerts.length > 0 && (
          <ul className="mt-3 divide-y divide-line">
            {alerts.map((alert) => (
              <StockRow key={alert.code} alert={alert} t={t} />
            ))}
          </ul>
        )}

        {stock.data?.generated_at && (
          <p className="mt-3 text-[11px] text-ink-faint">
            {t('ops.asOf', { time: timeOfDay(stock.data.generated_at) })}
          </p>
        )}

        <p className="mt-3 rounded border border-line bg-surface-sunken p-3 text-[11px] text-ink-muted">
          {t('stock.unknownNote')}
        </p>
      </section>
    </div>
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

function Counter({ label, value, urgent = false }: { label: string; value: number; urgent?: boolean }) {
  return (
    <div className="rounded border border-line bg-surface p-3">
      <dt className="text-xs uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd
        className={`mt-1 text-2xl font-semibold tabular-nums ${urgent ? 'text-urgent' : 'text-ink'}`}
      >
        {value}
      </dd>
    </div>
  );
}
