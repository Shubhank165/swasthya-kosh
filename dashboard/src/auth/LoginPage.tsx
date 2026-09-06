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
import { DASHBOARD_ROLES, useSession, type DashboardRole } from './session';

export function LoginPage() {
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
      <h1 className="text-xl font-semibold text-ink">MediKiosk</h1>
      <p className="mt-1 text-sm text-ink-muted">Clinical dashboard</p>

      {endedBecause === 'idle' && (
        <p
          role="status"
          className="mt-4 rounded border border-uncertain/30 bg-uncertain-soft px-3 py-2 text-sm text-uncertain"
        >
          Your session was cleared after a period without activity.
        </p>
      )}
      {endedBecause === 'refused' && (
        <p
          role="status"
          className="mt-4 rounded border border-urgent/30 bg-urgent-soft px-3 py-2 text-sm text-urgent"
        >
          The server refused that request. Sign in again.
        </p>
      )}

      <form onSubmit={submit} className="mt-6 space-y-4">
        <Field label="User ID" value={userId} onChange={setUserId} autoFocus required />
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-ink">Role</span>
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
        <Field label="Hospital ID" value={hospitalId} onChange={setHospitalId} required />
        <Field
          label="Department (optional)"
          value={department}
          onChange={setDepartment}
        />
        <button
          type="submit"
          className="w-full rounded bg-accent px-3 py-2 font-medium text-white hover:opacity-90"
        >
          Open the worklist
        </button>
      </form>

      <p className="mt-6 rounded border border-line bg-surface-sunken p-3 text-xs text-ink-muted">
        <strong className="text-ink">Stand-in sign-in.</strong> This screen sets
        the backend&rsquo;s header principal, which is disabled in any
        environment holding real patient data. It is not authentication and
        makes no claim to be; the hospital&rsquo;s identity provider replaces it
        and changes one file.
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
