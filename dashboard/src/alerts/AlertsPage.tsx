/**
 * Triage alerts — 3/3 §4.3, §1 rule 2.
 *
 * **Acknowledging is not escalating, and the two are never one button.** That
 * is the rule this file exists to hold. Acknowledging records that a person
 * looked; it notifies nobody, reorders nothing and authorises nothing.
 * Escalation is a decision a clinician makes and carries out — by walking to
 * the triage desk, in this hospital — and the most this screen may honestly do
 * is record that they said they did it.
 *
 * So escalation here is a second control, behind a second confirmation, and it
 * writes a *note on the acknowledgement* rather than pretending to page anyone.
 * A button labelled "escalate" that does nothing but change a colour is worse
 * than no button, because somebody will believe it.
 *
 * **Never a condition name.** Every rule carries the same fixed label from
 * `clinical/questions/redflags/` — "urgent clinical review criterion triggered"
 * — and this screen prints the rule's label and the criteria that met it,
 * nothing more.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { useAcknowledgeAlert, useAlerts } from '../api/queries';
import type { Alert } from '../api/types';
import { useSession } from '../auth/session';
import { dateAndTime, humanise } from '../lib/format';

export function AlertsPage() {
  const session = useSession((state) => state.session);
  // Everything by default, with the backend's unacknowledged-first ordering.
  //
  // Filtering to unacknowledged looks tidier and is worse: the card a physician
  // just acknowledged vanishes the instant the list refetches, leaving them
  // with no confirmation that the click was recorded and the next alert sitting
  // where their cursor was. Acknowledging should show the acknowledgement.
  const [hideAcknowledged, setHideAcknowledged] = useState(false);
  const alerts = useAlerts(
    hideAcknowledged ? false : null,
    session?.departmentCode ?? null,
  );

  const rows = alerts.data?.alerts ?? [];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold text-ink">Urgent review criteria</h1>
        <p className="text-sm text-ink-muted">
          Criteria that fired on the device during the interview. Unacknowledged
          first. The device screened a questionnaire; it did not examine anyone.
        </p>
      </header>

      <label className="flex items-center gap-2 text-sm text-ink-muted">
        <input
          type="checkbox"
          checked={hideAcknowledged}
          onChange={(event) => setHideAcknowledged(event.target.checked)}
        />
        Hide ones already acknowledged
      </label>

      {alerts.isLoading && <p className="text-ink-muted">Loading…</p>}
      {alerts.isError && (
        <p role="alert" className="text-urgent">
          Alerts could not be loaded.
        </p>
      )}

      <ul className="space-y-3">
        {rows.map((alert) => (
          <AlertCard key={alert.alert_id} alert={alert} />
        ))}
        {rows.length === 0 && !alerts.isLoading && (
          <li className="rounded border border-line bg-surface p-4 text-ink-muted">
            {hideAcknowledged
              ? 'Nothing outstanding.'
              : 'No criteria have fired in this window.'}
          </li>
        )}
      </ul>
    </div>
  );
}

function AlertCard({ alert }: { alert: Alert }) {
  const acknowledge = useAcknowledgeAlert();
  const [note, setNote] = useState('');
  const [confirmingEscalation, setConfirmingEscalation] = useState(false);
  const outstanding = alert.acknowledged_by === null || alert.acknowledged_by === undefined;

  const record = (escalated: boolean) =>
    acknowledge.mutate({
      intakeId: alert.intake_id,
      ruleId: alert.rule_id,
      note: escalated
        ? `escalated to triage in person${note ? `; ${note}` : ''}`
        : note || undefined,
    });

  return (
    <li
      data-testid="alert-card"
      data-alert-id={alert.alert_id}
      data-acknowledged={outstanding ? 'false' : 'true'}
      className={`rounded border p-4 ${
        outstanding
          ? 'border-urgent/40 bg-urgent-soft'
          : 'border-line bg-surface'
      }`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className={`text-sm font-semibold ${outstanding ? 'text-urgent' : 'text-ink'}`}>
          {/* The rule's own wording. Never a condition name. */}
          {alert.label ?? 'Urgent clinical review criterion triggered'}
        </h2>
        <span className="text-xs text-ink-muted">
          fired {dateAndTime(alert.received_at)}
          {alert.fired_at_turn !== null && alert.fired_at_turn !== undefined
            ? ` · turn ${alert.fired_at_turn}`
            : ''}
        </span>
      </div>

      <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-ink-muted">Intake</dt>
        <dd>
          <Link to={`/intakes/${alert.intake_id}`} className="text-accent underline">
            {alert.intake_id.slice(0, 8)}
          </Link>{' '}
          <span className="text-ink-faint">
            · {humanise(alert.intake_status)} · arrived{' '}
            {dateAndTime(alert.arrived_at)}
          </span>
        </dd>
        {/* The answers that met the rule. This is what lets a clinician judge
            it — the label alone says only that something fired. */}
        <dt className="text-ink-muted">Criteria met</dt>
        <dd className="text-ink">
          {(alert.criteria_met ?? []).map(humanise).join(', ') || '—'}
        </dd>
        <dt className="text-ink-muted">Rule</dt>
        <dd className="font-mono text-xs text-ink-muted">
          {alert.rule_id}
          {alert.engine_version ? ` · ${alert.engine_version}` : ''}
        </dd>
      </dl>

      {outstanding ? (
        <div className="mt-3 space-y-2">
          <label className="block text-sm">
            <span className="mb-1 block text-ink-muted">Note (optional)</span>
            <input
              value={note}
              onChange={(event) => setNote(event.target.value)}
              className="w-full rounded border border-line bg-surface px-2 py-1 text-ink"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {/* Two controls. Two clicks. They are never merged, and the second
                one is not a shortcut through the first. */}
            <button
              type="button"
              data-testid="acknowledge"
              disabled={acknowledge.isPending}
              onClick={() => record(false)}
              className="rounded border border-urgent px-3 py-1.5 text-sm font-medium text-urgent hover:bg-urgent/10"
            >
              Acknowledge — I have seen this
            </button>
            {confirmingEscalation ? (
              <button
                type="button"
                data-testid="escalate-confirm"
                disabled={acknowledge.isPending}
                onClick={() => record(true)}
                className="rounded bg-urgent px-3 py-1.5 text-sm font-medium text-white"
              >
                Confirm: I have escalated this to triage
              </button>
            ) : (
              <button
                type="button"
                data-testid="escalate"
                onClick={() => setConfirmingEscalation(true)}
                className="rounded border border-line px-3 py-1.5 text-sm text-ink hover:bg-surface-sunken"
              >
                Record an escalation
              </button>
            )}
          </div>
          <p className="text-xs text-ink-faint">
            Acknowledging records that you looked. It notifies nobody and moves
            nothing. Escalation is something you do, in person; this only
            records that you did.
          </p>
          {acknowledge.isError && (
            <p role="alert" className="text-sm text-urgent">
              That could not be recorded. It may already have been acknowledged
              by someone else — reload before acting.
            </p>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-ink-muted">
          Acknowledged by{' '}
          <span className="font-medium text-ink">{alert.acknowledged_by}</span> at{' '}
          {dateAndTime(alert.acknowledged_at)}
          {alert.acknowledgement_note ? ` — ${alert.acknowledgement_note}` : ''}
        </p>
      )}
    </li>
  );
}
