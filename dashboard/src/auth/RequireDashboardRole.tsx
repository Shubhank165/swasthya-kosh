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
import { useT } from '../i18n';
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
  const t = useT();

  if (session === null) return <LoginPage />;

  if (!canSeeClinicalContent(session)) {
    return (
      <Refusal
        titleKey="refusal.notClinicalTitle"
        detailKey="refusal.notClinical"
        onSignOut={() => signOut()}
      />
    );
  }

  if (allow && !allow.includes(session.role)) {
    return (
      <Refusal
        titleKey="refusal.roleTitle"
        // The role names stay in English in both locales: they are the words
        // the hospital's own systems use, and translating an identifier makes
        // it harder to match against a badge or an IdP group.
        detail={`${t('refusal.roleTitle')}: ${allow.join(' / ')}. ${t('refusal.detail')}`}
        onSignOut={() => signOut()}
      />
    );
  }

  return <>{children}</>;
}
