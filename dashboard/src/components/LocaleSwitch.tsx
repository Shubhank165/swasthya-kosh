/**
 * English or Hindi — 3/3 §9.
 *
 * A `<select>` rather than a pair of buttons: two languages today, nine in the
 * question bundle, and a control that grows without being redesigned is the one
 * to pick when the number is going to change.
 *
 * The choice is **not persisted**. §12 forbids storage here, and a shared OPD
 * terminal is why: a preference that survives the tab being closed is one the
 * next person to sit down inherits. The browser's own `Accept-Language` is the
 * default, which is right most of the time and costs nothing when it is not.
 */
import { LOCALES, LOCALE_NAMES, useLocale, useT, type Locale } from '../i18n';

export function LocaleSwitch() {
  const t = useT();
  const locale = useLocale((state) => state.locale);
  const setLocale = useLocale((state) => state.setLocale);

  return (
    <label className="flex items-center gap-1 text-xs text-ink-muted">
      <span className="sr-only">{t('common.language')}</span>
      <select
        value={locale}
        aria-label={t('common.language')}
        data-testid="locale-switch"
        onChange={(event) => setLocale(event.target.value as Locale)}
        className="rounded border border-line bg-surface px-1.5 py-0.5 text-ink"
      >
        {LOCALES.map((candidate) => (
          <option key={candidate} value={candidate}>
            {LOCALE_NAMES[candidate]}
          </option>
        ))}
      </select>
    </label>
  );
}
