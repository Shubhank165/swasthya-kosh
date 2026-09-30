/**
 * The front desk — who is waiting, in what order, and how long it has been.
 *
 * **This screen shows no clinical content and cannot.** A receptionist's role
 * is refused by the backend on every route that carries any: the report, the
 * record, the documents, the evidence, and `/alerts` — which looks harmless
 * and is not, because `criteria_met` names the answers that met a rule
 * ("breathlessness=true", "severity>=8"). That is a clinical fact about a
 * named person and the front desk does not need it.
 *
 * What the desk does need is that somebody is urgent, which the queue itself
 * says: a flagged intake carries its state and sorts to the top. "Urgent" and
 * "urgent because of this symptom" are different sentences, and only the first
 * one belongs here.
 *
 * So the rule this file follows: **render nothing a patient said.** Token,
 * arrival, wait, department, state. If a field could hold a symptom, it is not
 * on this screen.
 */
import { Link } from 'react-router-dom';

import { useWorklist } from '../api/queries';
import type { WorklistEntry } from '../api/types';
import { ConnectionState } from '../components/ConnectionState';
import { useSession } from '../auth/session';
import { useT, type Translate } from '../i18n';
import { useWorklistSocket } from '../lib/realtime';
import { humanise, timeOfDay } from '../lib/format';

/** Minutes between arrival and now, for a patient still waiting. */
function waitedMinutes(arrivedAt: string, now: number): number {
  const arrived = new Date(arrivedAt).getTime();
  if (Number.isNaN(arrived)) return 0;
  return Math.max(0, Math.round((now - arrived) / 60000));
}

export function ReceptionPage() {
  const t = useT();
  const session = useSession((state) => state.session);
  const department = session?.departmentCode ?? null;
  const worklist = useWorklist(department, []);
  const { status } = useWorklistSocket({
    department,
    onChange: () => void worklist.refetch(),
    enabled: true,
  });

  const entries = worklist.data?.entries ?? [];
  const now = Date.now();
  const waiting = entries.filter((entry) => entry.state !== 'seen');
  const flagged = waiting.filter((entry) => entry.state === 'red_flag_pending');

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink">{t('reception.title')}</h1>
          <p className="text-sm text-ink-muted">{t('reception.subtitle')}</p>
        </div>
        <ConnectionState status={status} />
      </header>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Counter label={t('reception.waiting')} value={waiting.length} />
        <Counter label={t('reception.flagged')} value={flagged.length} tone={flagged.length > 0 ? 'urgent' : 'plain'} />
        <Counter
          label={t('reception.longestWait')}
          value={
            waiting.length
              ? Math.max(...waiting.map((e) => waitedMinutes(e.arrived_at, now)))
              : 0
          }
          suffix={t('reception.minutes')}
        />
      </dl>

      <section className="surface-card p-5" aria-label={t('reception.queueAria')}>
        {worklist.isLoading && <p className="text-sm text-ink-muted">{t('common.loading')}</p>}

        {worklist.isError && (
          <p role="alert" className="text-xs font-semibold text-alert">
            {t('reception.loadError')}
          </p>
        )}

        {!worklist.isLoading && !worklist.isError && waiting.length === 0 && (
          <p className="text-sm text-ink-muted">{t('reception.nobodyWaiting')}</p>
        )}

        {waiting.length > 0 && (
          <table className="w-full text-sm" data-testid="reception-queue">
            <thead>
              <tr className="border-b border-line text-left text-[11px] uppercase tracking-[0.08em] text-ink-faint">
                <th className="py-1.5 font-semibold">{t('reception.position')}</th>
                <th className="py-1.5 font-semibold">{t('reception.token')}</th>
                <th className="py-1.5 font-semibold">{t('reception.department')}</th>
                <th className="py-1.5 font-semibold">{t('reception.arrived')}</th>
                <th className="py-1.5 font-semibold">{t('reception.waited')}</th>
                <th className="py-1.5 font-semibold">{t('reception.state')}</th>
              </tr>
            </thead>
            <tbody>
              {waiting.map((entry, index) => (
                <QueueRow
                  key={entry.intake_id}
                  entry={entry}
                  position={index + 1}
                  now={now}
                  t={t}
                />
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Said on screen rather than left to be discovered by clicking. A desk
          that does not know why it cannot open a record assumes the software
          is broken and asks somebody to fix it. */}
      <p className="rounded border border-line bg-surface-sunken p-3 text-[11px] text-ink-muted">
        {t('reception.noRecordsNote')}{' '}
        <Link to="/" className="underline">
          {t('reception.noRecordsLink')}
        </Link>
      </p>
    </div>
  );
}

function QueueRow({
  entry,
  position,
  now,
  t,
}: {
  entry: WorklistEntry;
  position: number;
  now: number;
  t: Translate;
}) {
  const flagged = entry.state === 'red_flag_pending';
  return (
    <tr
      className="border-b border-line/60 last:border-0"
      data-testid="reception-row"
      data-state={entry.state}
    >
      <td className="py-2 tabular-nums font-semibold text-ink">{position}</td>
      {/* The intake id, shortened. Not a name — this screen never holds one. */}
      <td className="py-2 font-mono text-xs text-ink-muted">
        {entry.intake_id.slice(0, 8)}
      </td>
      <td className="py-2 capitalize text-ink">
        {entry.department_code ? humanise(entry.department_code) : t('header.departmentNone')}
      </td>
      <td className="py-2 tabular-nums text-ink-muted">{timeOfDay(entry.arrived_at)}</td>
      <td className="py-2 tabular-nums text-ink">
        {t('reception.minutesValue', { minutes: waitedMinutes(entry.arrived_at, now) })}
      </td>
      <td className="py-2">
        {flagged ? (
          <span className="inline-flex items-center rounded border border-urgent/40 bg-urgent-soft px-1.5 py-0.5 text-xs font-semibold text-urgent">
            {t('reception.urgent')}
          </span>
        ) : (
          <span className="text-xs text-ink-muted">{t('reception.routine')}</span>
        )}
      </td>
    </tr>
  );
}

function Counter({
  label,
  value,
  suffix,
  tone = 'plain',
}: {
  label: string;
  value: number;
  suffix?: string;
  tone?: 'plain' | 'urgent';
}) {
  return (
    <div className="rounded border border-line bg-surface p-3">
      <dt className="text-xs uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd
        className={`mt-1 text-2xl font-semibold tabular-nums ${
          tone === 'urgent' ? 'text-urgent' : 'text-ink'
        }`}
      >
        {value}
        {suffix ? <span className="ml-1 text-sm font-medium">{suffix}</span> : null}
      </dd>
    </div>
  );
}
