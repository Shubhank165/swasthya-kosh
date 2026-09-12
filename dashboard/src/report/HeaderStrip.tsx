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

export const IDENTIFICATION: Record<string, StringKey> = {
  abha: 'id.abha',
  hospital_id: 'id.hospital_id',
  phone: 'id.phone',
  aadhaar_last4: 'id.aadhaar_last4',
  guest: 'id.guest',
};

/**
 * Chrome, not clinical content — so these live here and in `strings.ts` rather
 * than coming from the backend. A language tag and an intake status are facts
 * about the *record*, and naming them in the reader's language is the same act
 * as translating a column heading.
 */
const LANGUAGE_NAMES: Record<string, StringKey> = {
  en: 'lang.en',
  hi: 'lang.hi',
  bn: 'lang.bn',
  ta: 'lang.ta',
  te: 'lang.te',
  mr: 'lang.mr',
  gu: 'lang.gu',
  kn: 'lang.kn',
  pa: 'lang.pa',
};

export const INTAKE_STATUS: Record<string, StringKey> = {
  complete: 'intakeStatus.complete',
  partial: 'intakeStatus.partial',
  aborted_red_flag: 'intakeStatus.aborted_red_flag',
  abandoned: 'intakeStatus.abandoned',
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
        {/* Eight characters of a uuid, and the monospace says so: it is a
            handle to quote down a phone, not a number that means anything. */}
        <Item label={t('header.reference')}>
          <span className="font-mono text-sm tracking-tight">
            {intake.intake_id.slice(0, 8)}
          </span>
        </Item>
        <Item label={t('header.identifiedBy')}>
          {IDENTIFICATION[refType] ? t(IDENTIFICATION[refType]!) : humanise(refType)}
        </Item>
        {/* Which language the record below is in. Named, not tagged. */}
        <Item label={t('header.language')}>
          {LANGUAGE_NAMES[intake.language]
            ? t(LANGUAGE_NAMES[intake.language]!)
            : intake.language}
        </Item>
        <Item label={t('header.source')}>
          {refType === 'phone' ? t('header.sourceApp') : t('header.sourceKiosk')}
        </Item>
        <Item label={t('header.department')}>
          {intake.department_code ? humanise(intake.department_code) : '—'}
        </Item>
        <Item label={t('header.received')}>{dateAndTime(intake.received_at)}</Item>
        <Item label={t('header.intakeStatus')}>
          {INTAKE_STATUS[intake.status] ? t(INTAKE_STATUS[intake.status]!) : humanise(intake.status)}
        </Item>
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
