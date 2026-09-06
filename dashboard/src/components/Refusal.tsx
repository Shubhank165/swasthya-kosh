/**
 * What an under-privileged user sees — 3/3 §1 rule 6, §11 item 5.
 *
 * **Fail closed.** Not a partially rendered clinical screen with the sections
 * this role may not see quietly missing — a physician glancing at a colleague's
 * terminal cannot tell a short report from a censored one, and a report missing
 * its allergies section without saying so is worse than no report at all.
 *
 * So: a full-page refusal, no layout chrome, and nothing fetched behind it.
 */
import { useT, type StringKey } from '../i18n';

export function Refusal({
  titleKey = 'refusal.title',
  detailKey = 'refusal.detail',
  detail,
  onSignOut,
}: {
  titleKey?: StringKey;
  detailKey?: StringKey;
  /** Already-translated text, for the one case built from a role list. */
  detail?: string;
  onSignOut?: () => void;
}) {
  const t = useT();
  return (
    <main
      role="alert"
      data-testid="refusal"
      className="mx-auto mt-24 max-w-md rounded border border-line bg-surface p-6 text-center"
    >
      <h1 className="text-lg font-semibold text-ink">{t(titleKey)}</h1>
      <p className="mt-2 text-sm text-ink-muted">{detail ?? t(detailKey)}</p>
      {onSignOut && (
        <button
          type="button"
          onClick={onSignOut}
          className="mt-4 rounded border border-line px-3 py-1.5 text-sm text-ink hover:bg-surface-sunken"
        >
          {t('refusal.signOut')}
        </button>
      )}
    </main>
  );
}
