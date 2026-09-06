/**
 * The gate — 3/3 §1 rule 6, §8, §11 item 5.
 *
 * One component, wrapping everything clinical, so "who may see this screen" is
 * a single decision in a single place. A per-route check repeated in six files
 * is a check that is wrong in one of them.
 *
 * It renders a refusal rather than a redirect. A redirect to the sign-in screen
 * tells a `patient` token that it merely needs to try again; a refusal says the
 * account is wrong, which is true.
 */
import type { ReactNode } from 'react';
import { Refusal } from '../components/Refusal';
import { canSeeClinicalContent, useSession, type DashboardRole } from './session';
import { LoginPage } from './LoginPage';

export function RequireDashboardRole({
  children,
  allow,
}: {
  children: ReactNode;
  /** Narrower than the coarse gate, for screens like the correction rate. */
  allow?: readonly DashboardRole[];
}) {
  const session = useSession((state) => state.session);
  const signOut = useSession((state) => state.signOut);

  if (session === null) return <LoginPage />;

  if (!canSeeClinicalContent(session)) {
    return (
      <Refusal
        title="This account cannot open clinical records"
        detail="Patient and kiosk credentials are issued to a phone and to a device in a corridor. Neither may read a worklist or a report."
        onSignOut={() => signOut()}
      />
    );
  }

  if (allow && !allow.includes(session.role)) {
    return (
      <Refusal
        title="Not available to this role"
        detail={`This screen is limited to ${allow.join(' or ')}. Nothing has been loaded.`}
        onSignOut={() => signOut()}
      />
    );
  }

  return <>{children}</>;
}
