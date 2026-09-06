/**
 * Who this is and how much of the record was answered — 3/3 §4.2.
 *
 * Coverage reads as **"69 of 75 answered"**, the count and not a bare
 * percentage. 92% invites a physician to round it to "basically complete"; six
 * unanswered questions does not, and six is the number that decides whether
 * they need to ask anything themselves.
 *
 * The count is arithmetic over facts the backend sent, not a clinical
 * judgement: how many fields carry an answer, out of how many are on the
 * record. §1 rule 1 forbids deriving clinical content, and this derives none —
 * `unresolved_fields` and the fact list are both the backend's.
 */
import type { Intake } from '../api/types';
import { useT, type StringKey } from '../i18n';
import { dateAndTime, humanise } from '../lib/format';

const IDENTIFICATION: Record<string, StringKey> = {
  abha: 'id.abha',
  hospital_id: 'id.hospital_id',
  phone: 'id.phone',
  aadhaar_last4: 'id.aadhaar_last4',
  guest: 'id.guest',
};

export function HeaderStrip({ intake }: { intake: Intake }) {
  const t = useT();
  const facts = intake.facts ?? [];
  const answered = facts.filter((fact) => fact.status === 'answered').length;
  const total = facts.length;
  const refType = String(intake.patient_ref?.type ?? 'guest');
  const unacknowledged = (intake.red_flags ?? []).filter(
    (flag) => !flag.acknowledged_by,
  );

  return (
    <header className="rounded border border-line bg-surface p-3">
      {unacknowledged.length > 0 && (
        <p
          role="alert"
          data-testid="active-red-flag"
          className="mb-3 rounded border border-urgent/40 bg-urgent-soft px-3 py-2 text-sm font-medium text-urgent"
        >
          {unacknowledged.length === 1
            ? t('header.activeFlagsOne')
            : t('header.activeFlags', { count: unacknowledged.length })}
        </p>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
        <Item label={t('header.reference')}>
          <span className="font-mono">{intake.intake_id.slice(0, 8)}</span>
        </Item>
        <Item label={t('header.identifiedBy')}>
          {IDENTIFICATION[refType] ? t(IDENTIFICATION[refType]!) : humanise(refType)}
        </Item>
        {/* The intake language is a tag — `hi`, `ta` — not a word to translate:
            it says which language the record below is in. */}
        <Item label={t('header.language')}>{intake.language}</Item>
        <Item label={t('header.source')}>
          {refType === 'phone' ? t('header.sourceApp') : t('header.sourceKiosk')}
        </Item>
        <Item label={t('header.department')}>
          {intake.department_code ? humanise(intake.department_code) : '—'}
        </Item>
        <Item label={t('header.received')}>{dateAndTime(intake.received_at)}</Item>
        <Item label={t('header.intakeStatus')}>{humanise(intake.status)}</Item>
        <Item label={t('header.coverage')}>
          {/* The count, not a percentage. */}
          <span data-testid="coverage">
            {t('header.answered', { answered, total })}
          </span>
        </Item>
      </dl>

      {intake.demo && (
        <p className="mt-2 rounded border border-uncertain/30 bg-uncertain-soft px-2 py-1 text-xs text-uncertain">
          {t('header.demo')}
        </p>
      )}
    </header>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className="text-ink">{children}</dd>
    </div>
  );
}
