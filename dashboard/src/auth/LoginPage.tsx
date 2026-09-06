/**
 * Sign-in — 3/3 §8.
 *
 * **This form is a stand-in and says so on screen.** The backend's header
 * principal (`app/api/auth.py`) exists so the dashboard could be built before
 * the hospital's identity provider was integrated, and it is disabled in any
 * environment holding real data. A demo that quietly looked like a real login
 * would be claiming an integration this project does not have; the notice below
 * is the difference between a stand-in and a lie.
 *
 * `patient` and `kiosk` are not offered here and are refused if they arrive
 * anyway — see `canSeeClinicalContent` and `RequireDashboardRole`. Nothing is
 * written to localStorage, on this screen or any other.
 */
import { useState, type FormEvent } from 'react';
import { LocaleSwitch } from '../components/LocaleSwitch';
import { useT } from '../i18n';
import { DASHBOARD_ROLES, useSession, type DashboardRole } from './session';

export function LoginPage() {
  const t = useT();
  const signIn = useSession((state) => state.signIn);
  const endedBecause = useSession((state) => state.endedBecause);
  const [userId, setUserId] = useState('');
  const [role, setRole] = useState<DashboardRole>('physician');
  const [hospitalId, setHospitalId] = useState('aiia-delhi');
  const [department, setDepartment] = useState('');

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!userId.trim() || !hospitalId.trim()) return;
    signIn({
      userId: userId.trim(),
      role,
      hospitalId: hospitalId.trim(),
      departmentCode: department.trim() || null,
    });
  }

  return (
    <main className="mx-auto mt-20 max-w-sm">
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-ink">{t('app.name')}</h1>
          <p className="mt-1 text-sm text-ink-muted">{t('app.subtitle')}</p>
        </div>
        {/* Offered before sign-in, because a physician who reads Hindi should
            not have to read an English form to get to a Hindi screen. */}
        <LocaleSwitch />
      </div>

      {endedBecause === 'idle' && (
        <p
          role="status"
          className="mt-4 rounded border border-uncertain/30 bg-uncertain-soft px-3 py-2 text-sm text-uncertain"
        >
          {t('login.endedIdle')}
        </p>
      )}
      {endedBecause === 'refused' && (
        <p
          role="status"
          className="mt-4 rounded border border-urgent/30 bg-urgent-soft px-3 py-2 text-sm text-urgent"
        >
          {t('login.endedRefused')}
        </p>
      )}

      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field
          label={t('login.userId')}
          value={userId}
          onChange={setUserId}
          autoFocus
          required
        />
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">{t('login.role')}</span>
          <select
            value={role}
            onChange={(event) => setRole(event.target.value as DashboardRole)}
            className="w-full rounded border border-line bg-surface px-3 py-2 text-ink"
          >
            {DASHBOARD_ROLES.map((candidate) => (
              <option key={candidate} value={candidate}>
                {candidate}
              </option>
            ))}
          </select>
        </label>
        <Field
          label={t('login.hospitalId')}
          value={hospitalId}
          onChange={setHospitalId}
          required
        />
        <Field
          label={t('login.department')}
          value={department}
          onChange={setDepartment}
        />
        <button
          type="submit"
          className="w-full rounded bg-accent px-3 py-2 font-medium text-white hover:opacity-90"
        >
          {t('login.submit')}
        </button>
      </form>

      <p className="mt-6 rounded border border-line bg-surface-sunken p-3 text-xs text-ink-muted">
        <strong className="text-ink">{t('login.standInTitle')}</strong>{' '}
        {t('login.standIn')}
      </p>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
  autoFocus,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  autoFocus?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-ink">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        autoFocus={autoFocus}
        className="w-full rounded border border-line bg-surface px-3 py-2 text-ink"
      />
    </label>
  );
}
