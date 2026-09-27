/**
 * Chips for the two vocabularies coordination introduces.
 *
 * Shape and label, never colour alone — the same rule `StateChip` follows, and
 * for the same reason: a pharmacist reading a screen in OPD daylight should not
 * have to distinguish amber from red to know whether a box is expiring or
 * expired.
 *
 * **Nothing here decides anything.** Both the order status and the stock state
 * arrive decided from the backend; this file maps a value to a word and a
 * colour and does no arithmetic on either.
 */
import type { OrderStatus, StockState } from '../api/types';
import { useT, type Translate } from '../i18n';

const ORDER_STYLES: Record<OrderStatus, string> = {
  requested: 'border-line bg-surface-sunken text-ink-muted',
  scheduled: 'border-verified/30 bg-verified-soft text-verified',
  completed: 'border-verified/30 bg-verified-soft text-verified',
  cancelled: 'border-line bg-surface-sunken text-ink-faint',
  // Not a neutral state and not an error either: the hospital answered, and the
  // answer was no.
  unfilled: 'border-uncertain/40 bg-uncertain-soft text-uncertain',
};

const ORDER_LABELS: Record<OrderStatus, Parameters<Translate>[0]> = {
  requested: 'orders.status.requested',
  scheduled: 'orders.status.scheduled',
  completed: 'orders.status.completed',
  cancelled: 'orders.status.cancelled',
  unfilled: 'orders.status.unfilled',
};

export function OrderStatusChip({ status }: { status: OrderStatus }) {
  const t = useT();
  return (
    <span
      data-order-status={status}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${
        ORDER_STYLES[status] ?? ORDER_STYLES.requested
      }`}
    >
      {t(ORDER_LABELS[status] ?? 'orders.status.requested')}
    </span>
  );
}

const STOCK_STYLES: Record<StockState, string> = {
  available: 'border-verified/30 bg-verified-soft text-verified',
  low: 'border-uncertain/40 bg-uncertain-soft text-uncertain',
  expiring: 'border-uncertain/40 bg-uncertain-soft text-uncertain',
  expired: 'border-urgent/40 bg-urgent-soft text-urgent',
  out: 'border-urgent/40 bg-urgent-soft text-urgent',
  // Never reaches the alert list. Kept so a prescription check can render it.
  unknown: 'border-line bg-surface-sunken text-ink-muted',
};

const STOCK_LABELS: Record<StockState, Parameters<Translate>[0]> = {
  available: 'stock.state.available',
  low: 'stock.state.low',
  expiring: 'stock.state.expiring',
  expired: 'stock.state.expired',
  out: 'stock.state.out',
  unknown: 'stock.state.unknown',
};

export function StockStateChip({ state }: { state: StockState }) {
  const t = useT();
  return (
    <span
      data-stock-state={state}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${
        STOCK_STYLES[state] ?? STOCK_STYLES.unknown
      }`}
    >
      {t(STOCK_LABELS[state] ?? 'stock.state.unknown')}
    </span>
  );
}
