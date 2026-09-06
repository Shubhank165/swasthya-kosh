/**
 * The shell — routing, the session gate, and the idle clock.
 *
 * Everything clinical sits inside `RequireDashboardRole`, so there is exactly
 * one place that decides whether a screen renders or a refusal does (§1 rule 6).
 * The correction-rate view narrows that further to admin, matching the
 * backend's own guard rather than trusting it.
 */
import { NavLink, Route, Routes } from 'react-router-dom';

import { AlertsPage } from './alerts/AlertsPage';
import { LocaleSwitch } from './components/LocaleSwitch';
import { useT } from './i18n';
import { MetricsPage } from './admin/MetricsPage';
import { RequireDashboardRole } from './auth/RequireDashboardRole';
import { useIdleTimeout } from './auth/useIdleTimeout';
import { useSession } from './auth/session';
import { ReportPage } from './report/ReportPage';
import { WorklistPage } from './worklist/WorklistPage';

export function App() {
  const session = useSession((state) => state.session);

  return (
    <RequireDashboardRole>
      <div className="min-h-screen">
        <TopBar />
        <IdleWarning enabled={session !== null} />
        <main className="mx-auto max-w-7xl p-4">
          <Routes>
            <Route path="/" element={<WorklistPage />} />
            <Route path="/alerts" element={<AlertsPage />} />
            <Route path="/intakes/:intakeId" element={<ReportPage />} />
            <Route
              path="/metrics"
              element={
                <RequireDashboardRole allow={['admin']}>
                  <MetricsPage />
                </RequireDashboardRole>
              }
            />
            <Route path="*" element={<NoSuchScreen />} />
          </Routes>
        </main>
      </div>
    </RequireDashboardRole>
  );
}

function NoSuchScreen() {
  const t = useT();
  return <p className="text-ink-muted">{t('nav.noScreen')}</p>;
}

function TopBar() {
  const t = useT();
  const session = useSession((state) => state.session);
  const signOut = useSession((state) => state.signOut);

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-2">
        <span className="font-semibold text-ink">{t('app.name')}</span>
        <nav className="flex gap-3 text-sm">
          <Tab to="/" label={t('nav.worklist')} />
          <Tab to="/alerts" label={t('nav.alerts')} />
          {session?.role === 'admin' && <Tab to="/metrics" label={t('nav.quality')} />}
        </nav>
        <span className="ml-auto text-xs text-ink-muted">
          {/* The user id, the role and the hospital id, untranslated: they are
              identifiers, and a physician checking they are signed in as
              themselves needs the string their badge says. */}
          {session?.userId} · {session?.role} · {session?.hospitalId}
        </span>
        <LocaleSwitch />
        <button
          type="button"
          onClick={() => signOut()}
          className="rounded border border-line px-2 py-1 text-xs text-ink hover:bg-surface-sunken"
        >
          {t('nav.signOut')}
        </button>
      </div>
    </header>
  );
}

function Tab({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        isActive ? 'font-medium text-accent' : 'text-ink-muted hover:text-ink'
      }
    >
      {label}
    </NavLink>
  );
}

/**
 * The idle warning — §8.
 *
 * A banner rather than a modal. A physician mid-amendment should be able to
 * keep typing and have the warning go away by itself, which is what typing
 * does; a modal would take the keystroke that dismissed it.
 */
function IdleWarning({ enabled }: { enabled: boolean }) {
  const t = useT();
  const { warning, secondsLeft, staySignedIn } = useIdleTimeout(enabled);
  if (!warning) return null;
  return (
    <div
      role="status"
      data-testid="idle-warning"
      className="border-b border-uncertain/40 bg-uncertain-soft px-4 py-2 text-sm text-uncertain"
    >
      {t('idle.warning', { seconds: secondsLeft ?? 0 })}{' '}
      <button type="button" onClick={staySignedIn} className="underline">
        {t('idle.stay')}
      </button>
    </div>
  );
}
