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
import { useT } from '../i18n';
import { dateAndTime, humanise } from '../lib/format';

export function AlertsPage() {
  const t = useT();
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
        <h1 className="text-lg font-semibold text-ink">{t('alerts.title')}</h1>
        <p className="text-sm text-ink-muted">{t('alerts.subtitle')}</p>
      </header>

      <label className="flex items-center gap-2 text-sm text-ink-muted">
        <input
          type="checkbox"
          checked={hideAcknowledged}
          onChange={(event) => setHideAcknowledged(event.target.checked)}
        />
        {t('alerts.hideAcknowledged')}
      </label>

      {alerts.isLoading && <p className="text-ink-muted">{t('common.loading')}</p>}
      {alerts.isError && (
        <p role="alert" className="text-urgent">
          {t('alerts.error')}
        </p>
      )}

      <ul className="space-y-3">
        {rows.map((alert) => (
          <AlertCard key={alert.alert_id} alert={alert} />
        ))}
        {rows.length === 0 && !alerts.isLoading && (
          <li className="rounded border border-line bg-surface p-4 text-ink-muted">
            {t(hideAcknowledged ? 'alerts.noneOutstanding' : 'alerts.noneFired')}
          </li>
        )}
      </ul>
    </div>
  );
}

function AlertCard({ alert }: { alert: Alert }) {
  const t = useT();
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
          {/* **The rule's own wording, from the content, and never
              translated here.** It is a clinical string an AIIA mentor signs
              off; a locale switch is not the place to reword it, and §B4 has a
              queue for the ones that need a clinician. The fallback below is
              the same fixed wording every rule in `clinical/questions/redflags/`
              already carries. */}
          {alert.label ?? t('alerts.defaultLabel')}
        </h2>
        <span className="text-xs text-ink-muted">
          {t('alerts.fired', { when: dateAndTime(alert.received_at) })}
          {alert.fired_at_turn !== null && alert.fired_at_turn !== undefined
            ? ` · ${t('alerts.turn', { turn: alert.fired_at_turn })}`
            : ''}
        </span>
      </div>

      <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-ink-muted">{t('alerts.intake')}</dt>
        <dd>
          <Link to={`/intakes/${alert.intake_id}`} className="text-accent underline">
            {alert.intake_id.slice(0, 8)}
          </Link>{' '}
          <span className="text-ink-faint">
            · {humanise(alert.intake_status)} · {t('alerts.arrived')}{' '}
            {dateAndTime(alert.arrived_at)}
          </span>
        </dd>
        {/* The answers that met the rule. This is what lets a clinician judge
            it — the label alone says only that something fired. */}
        <dt className="text-ink-muted">{t('alerts.criteria')}</dt>
        <dd className="text-ink">
          {(alert.criteria_met ?? []).map(humanise).join(', ') || '—'}
        </dd>
        <dt className="text-ink-muted">{t('alerts.rule')}</dt>
        <dd className="font-mono text-xs text-ink-muted">
          {alert.rule_id}
          {alert.engine_version ? ` · ${alert.engine_version}` : ''}
        </dd>
      </dl>

      {outstanding ? (
        <div className="mt-3 space-y-2">
          <label className="block text-sm">
            <span className="mb-1 block text-ink-muted">{t('alerts.note')}</span>
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
              {t('alerts.acknowledge')}
            </button>
            {confirmingEscalation ? (
              <button
                type="button"
                data-testid="escalate-confirm"
                disabled={acknowledge.isPending}
                onClick={() => record(true)}
                className="rounded bg-urgent px-3 py-1.5 text-sm font-medium text-white"
              >
                {t('alerts.escalateConfirm')}
              </button>
            ) : (
              <button
                type="button"
                data-testid="escalate"
                onClick={() => setConfirmingEscalation(true)}
                className="rounded border border-line px-3 py-1.5 text-sm text-ink hover:bg-surface-sunken"
              >
                {t('alerts.escalate')}
              </button>
            )}
          </div>
          <p className="text-xs text-ink-faint">{t('alerts.twoActs')}</p>
          {acknowledge.isError && (
            <p role="alert" className="text-sm text-urgent">
              {t('alerts.conflict')}
            </p>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-ink-muted">
          {t('alerts.acknowledgedBy', {
            actor: alert.acknowledged_by ?? '',
            when: dateAndTime(alert.acknowledged_at),
          })}
          {alert.acknowledgement_note ? ` — ${alert.acknowledgement_note}` : ''}
        </p>
      )}
    </li>
  );
}
