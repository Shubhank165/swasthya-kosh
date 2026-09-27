/**
 * What the doctor asked for, after the consultation.
 *
 * The report ends at the door of the room. A test, a scan, a referral and a
 * prescription are what happen next, and until this panel they left the system
 * as paper. Four things are on screen and each is there for a reason:
 *
 * - **Every order, with its status.** A referral that found no capacity shows
 *   as *no slot available* rather than as a pending request with a blank time.
 *   That distinction is the feature; flattening it here would throw away the
 *   only thing the slot table is for.
 * - **The time, when there is one.** Never a placeholder where a slot is
 *   missing — a patient sent across a hospital to a time nobody offered is the
 *   failure this is meant to prevent.
 * - **Issuing**, for a physician only. The backend enforces that; this only
 *   avoids rendering a control that would be refused.
 * - **The queue position**, which is the one number the patient asks for.
 *
 * Nothing here computes a status, a slot or a wait. All four arrive decided —
 * §1 rule 1, which applies to this panel exactly as it does to the report.
 */
import { useState } from 'react';

import { useIssueOrder, useOrders, useWaitEstimate } from '../api/queries';
import type { CareOrder, OrderKind } from '../api/types';
import { useSession } from '../auth/session';
import { useT, type Translate } from '../i18n';
import { dateAndTime } from '../lib/format';
import { OrderStatusChip } from './chips';

const KINDS: readonly OrderKind[] = ['lab', 'imaging', 'referral', 'prescription'];

const KIND_LABELS: Record<OrderKind, Parameters<Translate>[0]> = {
  lab: 'orders.kind.lab',
  imaging: 'orders.kind.imaging',
  referral: 'orders.kind.referral',
  prescription: 'orders.kind.prescription',
};

export function OrdersPanel({ intakeId }: { intakeId: string }) {
  const t = useT();
  const session = useSession((state) => state.session);
  const canIssue = session?.role === 'physician' || session?.role === 'admin';
  const orders = useOrders(intakeId);
  const rows = orders.data?.orders ?? [];

  return (
    <section
      className="surface-card p-6"
      aria-label={t('orders.aria')}
      data-testid="orders-panel"
    >
      <header className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-ink">{t('orders.title')}</h2>
        <WaitLine intakeId={intakeId} />
      </header>
      <p className="mb-4 text-xs text-ink-muted">{t('orders.subtitle')}</p>

      {orders.isError && (
        <p role="alert" className="text-xs font-semibold text-alert">
          {t('orders.loadError')}
        </p>
      )}

      {orders.isLoading && <p className="text-sm text-ink-muted">{t('common.loading')}</p>}

      {/* Said only once the answer is in. "Nothing has been ordered" while the
          request is still running is a statement about the patient that nobody
          has checked. */}
      {!orders.isLoading && !orders.isError && rows.length === 0 && (
        <p className="text-sm text-ink-muted">{t('orders.none')}</p>
      )}

      {rows.length > 0 && (
        <ul className="divide-y divide-line" data-testid="orders-list">
          {rows.map((order) => (
            <OrderRow key={order.id} order={order} t={t} />
          ))}
        </ul>
      )}

      {canIssue && <IssueForm intakeId={intakeId} t={t} />}
    </section>
  );
}

function OrderRow({ order, t }: { order: CareOrder; t: Translate }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5" data-order-id={order.id}>
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
        {t(KIND_LABELS[order.kind] ?? 'orders.kind.lab')}
      </span>
      <span className="font-medium text-ink">{order.display}</span>
      <OrderStatusChip status={order.status} />
      {order.destination && (
        <span className="text-xs text-ink-muted">{order.destination}</span>
      )}
      <span className="ml-auto text-xs tabular-nums text-ink-muted">
        {/* A time only when one was actually offered. `unfilled` renders the
            words, not an em dash that reads as "loading". */}
        {order.slot_at
          ? dateAndTime(order.slot_at)
          : order.status === 'unfilled'
            ? t('orders.noSlot')
            : ''}
      </span>
    </li>
  );
}

/**
 * The queue position, and a time only when the backend stands behind one.
 *
 * `confident: false` is rendered as a position with no minutes and a sentence
 * saying why. It is deliberately not rounded up into "a few minutes": a waiting
 * room given a number that turns out wrong stops believing the screen, and then
 * the honest estimates stop working too.
 */
function WaitLine({ intakeId }: { intakeId: string }) {
  const t = useT();
  const wait = useWaitEstimate(intakeId);
  if (!wait.data) return null;
  const { position, minutes, confident } = wait.data;
  return (
    <span className="text-xs text-ink-muted" data-testid="wait-estimate">
      <span className="font-semibold text-ink">{t('wait.position', { position })}</span>
      {confident && minutes !== null && minutes !== undefined ? (
        <> · {t('wait.minutes', { minutes })}</>
      ) : (
        <> · {t('wait.noEstimate')}</>
      )}
    </span>
  );
}

/**
 * Issue one order.
 *
 * A code and a label are both required, and neither is derived from the other:
 * a code nobody can read is not a handover, and a label nobody can resolve is
 * not a record. The destination is optional because a prescription has none —
 * the pharmacy counter has no appointment to offer.
 */
function IssueForm({ intakeId, t }: { intakeId: string; t: Translate }) {
  const issue = useIssueOrder(intakeId);
  const [kind, setKind] = useState<OrderKind>('lab');
  const [code, setCode] = useState('');
  const [display, setDisplay] = useState('');
  const [destination, setDestination] = useState('');

  const ready = code.trim() !== '' && display.trim() !== '';

  return (
    <form
      data-testid="issue-order"
      className="mt-5 border-t border-line pt-4 print:hidden"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ready) return;
        issue.mutate(
          {
            kind,
            code: code.trim(),
            display: display.trim(),
            ...(destination.trim() ? { destination: destination.trim() } : {}),
          },
          {
            onSuccess: () => {
              setCode('');
              setDisplay('');
              setDestination('');
            },
          },
        );
      }}
    >
      <div className="flex flex-wrap items-end gap-2">
        <Field label={t('orders.field.kind')}>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as OrderKind)}
            className="rounded-lg border border-line bg-white px-2 py-1.5 text-sm text-ink"
          >
            {KINDS.map((option) => (
              <option key={option} value={option}>
                {t(KIND_LABELS[option])}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('orders.field.code')}>
          <input
            value={code}
            onChange={(event) => setCode(event.target.value)}
            className="w-36 rounded-lg border border-line bg-white px-2 py-1.5 text-sm text-ink"
          />
        </Field>
        <Field label={t('orders.field.display')}>
          <input
            value={display}
            onChange={(event) => setDisplay(event.target.value)}
            className="w-52 rounded-lg border border-line bg-white px-2 py-1.5 text-sm text-ink"
          />
        </Field>
        <Field label={t('orders.field.destination')}>
          <input
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
            className="w-40 rounded-lg border border-line bg-white px-2 py-1.5 text-sm text-ink"
          />
        </Field>
        <button
          type="submit"
          disabled={!ready || issue.isPending}
          data-testid="issue-order-submit"
          className="rounded-xl bg-herb px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-herb-deep disabled:opacity-50"
        >
          {issue.isPending ? t('common.loading') : t('orders.issue')}
        </button>
      </div>

      {issue.isError && (
        <p role="alert" className="mt-2 text-xs font-semibold text-alert">
          {t('orders.issueError')}
        </p>
      )}
      <p className="mt-2 text-[11px] text-ink-muted">{t('orders.slotNote')}</p>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-faint">
        {label}
      </span>
      {children}
    </label>
  );
}
