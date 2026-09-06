/**
 * The worklist — 3/3 §4.1.
 *
 * A list the doctor works down. **Not queue management**: no calling,
 * recalling, deferring, transferring or token issuing. `stale/queue/` holds a
 * version of that, the problem statement does not ask for it, and every line of
 * it is surface area to defend without marks attached.
 *
 * Ordering is arrival, and stays arrival. The alert band at the top is how
 * urgency is surfaced — the backend puts unacknowledged red flags in
 * `pending_alerts` and the list itself is not reordered, because reordering a
 * waiting room on a machine's reading of a symptom is a triage decision this
 * system does not make.
 *
 * A real `<table>` with real headers, per §9. A grid of divs is not navigable
 * by anything but a mouse.
 */
import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';

import { useWorklist } from '../api/queries';
import type { WorklistEntry, WorklistState } from '../api/types';
import { WORKLIST_STATES } from '../api/types';
import { useSession } from '../auth/session';
import { ConnectionState } from '../components/ConnectionState';
import { useT, type StringKey, type Translate } from '../i18n';
import { useWorklistSocket } from '../lib/realtime';
import { humanise, timeOfDay } from '../lib/format';

const STATE_KEYS: Record<WorklistState, StringKey> = {
  ready: 'state.ready',
  partial: 'state.partial',
  red_flag_pending: 'state.red_flag_pending',
  needs_review: 'state.needs_review',
  seen: 'state.seen',
};

/** Shape, not colour alone — §4.2, and the same rule applies to the list. */
const STATE_STYLES: Record<WorklistState, string> = {
  ready: 'border-line bg-surface-sunken text-ink-muted',
  partial: 'border-uncertain/30 bg-uncertain-soft text-uncertain',
  red_flag_pending: 'border-urgent/40 bg-urgent-soft text-urgent',
  needs_review: 'border-repaired/30 bg-repaired-soft text-repaired',
  seen: 'border-verified/30 bg-verified-soft text-verified',
};

export function WorklistPage({ realtime = true }: { realtime?: boolean }) {
  const t = useT();
  const session = useSession((state) => state.session);
  const [department, setDepartment] = useState<string | null>(
    session?.departmentCode ?? null,
  );
  const [states, setStates] = useState<readonly WorklistState[]>([]);

  const worklist = useWorklist(department, states);
  const refetch = worklist.refetch;

  // §7: on reconnect, refetch rather than replay. The socket says *something*
  // changed; the list comes from the API, which is the only thing that knows
  // what the change was.
  const onChange = useCallback(() => {
    void refetch();
  }, [refetch]);
  const { status } = useWorklistSocket({ department, onChange, enabled: realtime });

  const entries = worklist.data?.entries ?? [];
  const pending = worklist.data?.pending_alerts ?? [];
  const hidden = (worklist.data?.total ?? 0) - entries.length;

  const toggleState = (state: WorklistState) =>
    setStates((current) =>
      current.includes(state)
        ? current.filter((candidate) => candidate !== state)
        : [...current, state],
    );

  // A plain filter rather than a memo: `entries` is a fresh array on every
  // render because it comes out of a `??`, so memoising on it would recompute
  // every time anyway while looking like it did not.
  const needsManualReview = entries.filter((entry) => entry.needs_manual_review);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink">{t('worklist.title')}</h1>
          <p className="text-sm text-ink-muted">
            {/* The department code is the hospital's own identifier and is not
                translated; the words around it are. */}
            {department ? humanise(department) : t('worklist.allDepartments')} ·{' '}
            {t('worklist.arrivalOrder')}
          </p>
        </div>
        <ConnectionState status={status} />
      </header>

      {/* The pinned band. Separate from the list rather than sorted into it, so
          urgency is visible without pretending the queue was rearranged. */}
      {pending.length > 0 && (
        <section
          aria-label={t('worklist.alertBandLabel')}
          data-testid="alert-band"
          className="rounded border border-urgent/40 bg-urgent-soft p-3"
        >
          <h2 className="text-sm font-semibold text-urgent">
            {pending.length === 1
              ? t('worklist.alertBandOne')
              : t('worklist.alertBand', { count: pending.length })}
          </h2>
          <ul className="mt-2 space-y-1">
            {pending.map((entry) => (
              <li key={entry.intake_id}>
                <Link
                  to={`/intakes/${entry.intake_id}`}
                  className="text-sm text-urgent underline"
                >
                  {entry.intake_id.slice(0, 8)} · {t('worklist.arrived')}{' '}
                  {timeOfDay(entry.arrived_at)}
                </Link>
              </li>
            ))}
          </ul>
          <Link to="/alerts" className="mt-2 inline-block text-xs text-urgent underline">
            {t('worklist.openAlerts')}
          </Link>
        </section>
      )}

      {needsManualReview.length > 0 && (
        <p className="rounded border border-repaired/30 bg-repaired-soft px-3 py-2 text-sm text-repaired">
          {t('worklist.manualReview', { count: needsManualReview.length })}
        </p>
      )}

      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">{t('worklist.filterLegend')}</legend>
        <label className="text-sm text-ink-muted">
          {t('worklist.department')}{' '}
          <input
            value={department ?? ''}
            onChange={(event) => setDepartment(event.target.value || null)}
            placeholder={t('worklist.departmentAll')}
            className="ml-1 rounded border border-line bg-surface px-2 py-1 text-ink"
          />
        </label>
        {WORKLIST_STATES.map((state) => (
          <label key={state} className="flex items-center gap-1 text-sm text-ink-muted">
            <input
              type="checkbox"
              checked={states.includes(state)}
              onChange={() => toggleState(state)}
            />
            {t(STATE_KEYS[state])}
          </label>
        ))}
      </fieldset>

      {worklist.isLoading && <p className="text-ink-muted">{t('common.loading')}</p>}
      {worklist.isError && (
        <p role="alert" className="text-urgent">
          {t('worklist.error')}
        </p>
      )}

      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{t('worklist.caption')}</caption>
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-muted">
            <th scope="col" className="py-2 pr-3">{t('worklist.colReference')}</th>
            <th scope="col" className="py-2 pr-3">{t('worklist.colArrived')}</th>
            <th scope="col" className="py-2 pr-3">{t('worklist.colSource')}</th>
            <th scope="col" className="py-2 pr-3">{t('worklist.colIntake')}</th>
            <th scope="col" className="py-2 pr-3">{t('worklist.colState')}</th>
            <th scope="col" className="py-2 pr-3">{t('worklist.colUnresolved')}</th>
            <th scope="col" className="py-2 pr-3">{t('worklist.colConflicts')}</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <Row key={entry.intake_id} entry={entry} t={t} />
          ))}
          {entries.length === 0 && !worklist.isLoading && (
            <tr>
              <td colSpan={7} className="py-6 text-center text-ink-muted">
                {t('worklist.empty')}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* A filter that hides thirty patients says so, rather than making the
          department look quiet. */}
      {hidden > 0 && (
        <p className="text-xs text-ink-muted">
          {t('worklist.hidden', { count: hidden })}
        </p>
      )}
    </div>
  );
}

function Row({ entry, t }: { entry: WorklistEntry; t: Translate }) {
  const state = entry.state as WorklistState;
  return (
    <tr className="border-b border-line/60 hover:bg-surface-sunken">
      <td className="py-2 pr-3">
        <Link
          to={`/intakes/${entry.intake_id}`}
          className="font-medium text-accent underline"
          data-testid="worklist-row"
          data-intake-id={entry.intake_id}
        >
          {entry.intake_id.slice(0, 8)}
        </Link>
        {/* How the patient was identified, not who they are. This table can be
            visible from a waiting room. */}
        <span className="ml-2 text-xs text-ink-faint">{entry.patient_ref_type}</span>
      </td>
      <td className="py-2 pr-3 tabular-nums text-ink-muted">
        {timeOfDay(entry.arrived_at)}
      </td>
      <td className="py-2 pr-3 text-ink-muted">{sourceOf(entry, t)}</td>
      <td className="py-2 pr-3 text-ink-muted">{humanise(entry.intake_status)}</td>
      <td className="py-2 pr-3">
        <span
          data-state={state}
          className={`inline-flex rounded border px-1.5 py-0.5 text-xs font-medium ${STATE_STYLES[state]}`}
        >
          {STATE_KEYS[state] ? t(STATE_KEYS[state]) : state}
          {entry.unacknowledged_alerts > 0 && ` (${entry.unacknowledged_alerts})`}
        </span>
      </td>
      <td className="py-2 pr-3 tabular-nums text-ink-muted">
        {entry.unresolved_count}
      </td>
      <td className="py-2 pr-3 tabular-nums text-ink-muted">
        {entry.contradiction_count}
      </td>
    </tr>
  );
}

/**
 * Kiosk or app.
 *
 * Derived from the patient reference, which is the only signal the worklist row
 * carries: a phone-referenced intake came from the app, because a kiosk in a
 * corridor has no phone number to sign in with. Stated as an inference rather
 * than dressed up as a field the backend sent.
 */
function sourceOf(entry: WorklistEntry, t: Translate): string {
  return entry.patient_ref_type === 'phone'
    ? t('worklist.sourceApp')
    : t('worklist.sourceKiosk');
}
