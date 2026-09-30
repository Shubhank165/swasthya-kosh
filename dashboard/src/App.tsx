/**
 * The shell — routing, the session gate, and the idle clock.
 *
 * Everything clinical sits inside `RequireDashboardRole`, so there is exactly
 * one place that decides whether a screen renders or a refusal does (§1 rule 6).
 * The correction-rate view narrows that further to admin, matching the
 * backend's own guard rather than trusting it.
 */
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { HeartPulse, LogOut } from 'lucide-react';

import { AlertsPage } from './alerts/AlertsPage';
import { LocaleSwitch } from './components/LocaleSwitch';
import { useT } from './i18n';
import type { StringKey } from './i18n/strings';
import { MetricsPage } from './admin/MetricsPage';
import { OperationsPage } from './coordination/OperationsPage';
import { PharmacyPage } from './pharmacy/PharmacyPage';
import { ReceptionPage } from './reception/ReceptionPage';
import { RequireDashboardRole } from './auth/RequireDashboardRole';
import { useIdleTimeout } from './auth/useIdleTimeout';
import { useSession, type DashboardRole } from './auth/session';
import { ReportPage } from './report/ReportPage';
import { WorklistPage } from './worklist/WorklistPage';

/**
 * Every screen, who may see it, and whether it gets a nav tab.
 *
 * One table rather than a hardcoded list plus an inline `role === 'admin'`
 * check: with five roles the inline form is where a screen quietly ends up
 * reachable by somebody it was never meant for.
 */
const CLINICAL: readonly DashboardRole[] = ['physician', 'staff', 'admin'];

const SCREENS: {
  path: string;
  element: (props: Record<string, never>) => JSX.Element;
  roles: readonly DashboardRole[];
  tab?: StringKey;
}[] = [
  { path: '/', element: WorklistPage, roles: CLINICAL, tab: 'nav.worklist' },
  { path: '/queue', element: WorklistPage, roles: CLINICAL },
  { path: '/alerts', element: AlertsPage, roles: CLINICAL, tab: 'nav.alerts' },
  { path: '/intakes/:intakeId', element: ReportPage, roles: CLINICAL },
  { path: '/patient/:intakeId', element: ReportPage, roles: CLINICAL },
  {
    path: '/reception',
    element: ReceptionPage,
    roles: ['receptionist', 'admin'],
    tab: 'nav.reception',
  },
  {
    path: '/pharmacy',
    element: PharmacyPage,
    roles: ['chemist', 'admin'],
    tab: 'nav.pharmacy',
  },
  { path: '/operations', element: OperationsPage, roles: ['admin'], tab: 'nav.operations' },
  { path: '/metrics', element: MetricsPage, roles: ['admin'], tab: 'nav.quality' },
];

/** Where each role lands when they sign in. */
const HOME_FOR: Record<DashboardRole, string> = {
  physician: '/',
  staff: '/',
  admin: '/',
  receptionist: '/reception',
  chemist: '/pharmacy',
};

export function App() {
  const session = useSession((state) => state.session);

  return (
    <RequireDashboardRole>
      <div className="min-h-screen bg-[#f8faf9]">
        <TopBar />
        <IdleWarning enabled={session !== null} />
        <main className="mx-auto max-w-7xl px-4 py-6 print:max-w-none print:p-0">
          <Routes>
            {/* Every screen names the roles that may see it. The outer
                wrapper only establishes that somebody is signed in — a
                receptionist and a pharmacist both are, and neither may read a
                record, so a route left ungated here would be a leak. */}
            {SCREENS.map(({ path, element: Element, roles }) => (
              <Route
                key={path}
                path={path}
                element={
                  <RequireDashboardRole allow={roles}>
                    <Element />
                  </RequireDashboardRole>
                }
              />
            ))}
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

  const initials = session?.userId
    ? session.userId.slice(0, 2).toUpperCase()
    : 'DR';

  return (
    <header className="sticky top-0 z-30 border-b border-line/80 bg-white/95 backdrop-blur print:hidden">
      <div className="tricolour-rule h-1 w-full" />
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link to={session ? HOME_FOR[session.role] : "/"} className="flex items-center gap-3">
          <span className="brand-gradient flex size-10 items-center justify-center rounded-xl text-white shadow-sm">
            <HeartPulse className="size-5" />
          </span>
          <span className="leading-tight">
            <span className="block font-semibold text-ink text-base">MediKiosk</span>
            <span className="block text-[10px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
              {t('app.subtitle')}
            </span>
          </span>
        </Link>

        <nav className="ml-6 hidden items-center gap-1 md:flex">
          {SCREENS.filter(
            (screen) => screen.tab && session && screen.roles.includes(session.role),
          ).map((screen) => (
            <Tab key={screen.path} to={screen.path} label={t(screen.tab!)} />
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <LocaleSwitch />

          <div className="hidden items-center gap-2.5 border-l border-line pl-3 sm:flex">
            <span className="flex size-9 items-center justify-center rounded-full bg-brand-soft text-xs font-bold text-brand">
              {initials}
            </span>
            <span className="leading-tight">
              <span className="block text-xs font-semibold text-ink">
                {session?.userId ?? 'Doctor'}
              </span>
              <span className="block text-[10px] text-ink-muted capitalize">
                {session?.role} • {session?.hospitalId ?? 'Hospital'}
              </span>
            </span>
          </div>

          <button
            type="button"
            onClick={() => signOut()}
            className="flex size-9 items-center justify-center rounded-lg border border-line text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink"
            aria-label={t('nav.signOut')}
            title={t('nav.signOut')}
          >
            <LogOut className="size-4" />
          </button>
        </div>
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
        `rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
          isActive
            ? 'bg-brand-soft text-brand font-semibold'
            : 'text-ink-muted hover:bg-surface-sunken hover:text-ink'
        }`
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
