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
import { Globe } from 'lucide-react';
import { useLocale, useT, type Locale } from '../i18n';

const ALL_LANGUAGES = [
  { code: 'en', name: 'English', active: true },
  { code: 'hi', name: 'हिंदी (Hindi)', active: true },
  { code: 'ta', name: 'தமிழ் (Tamil)', active: false },
  { code: 'te', name: 'తెలుగు (Telugu)', active: false },
  { code: 'bn', name: 'বাংলা (Bengali)', active: false },
  { code: 'mr', name: 'मराठी (Marathi)', active: false },
  { code: 'gu', name: 'ગુજરાતી (Gujarati)', active: false },
];

export function LocaleSwitch() {
  const t = useT();
  const locale = useLocale((state) => state.locale);
  const setLocale = useLocale((state) => state.setLocale);

  return (
    <div className="relative inline-flex items-center">
      <Globe className="pointer-events-none absolute left-2.5 size-3.5 text-ink-muted" />
      <select
        value={locale}
        aria-label={t('common.language')}
        data-testid="locale-switch"
        onChange={(event) => {
          const val = event.target.value;
          if (val === 'en' || val === 'hi') {
            setLocale(val as Locale);
          }
        }}
        className="h-8 rounded-full border border-line bg-white/90 py-1 pl-8 pr-3 text-xs font-medium text-ink shadow-sm outline-none transition-colors hover:border-herb focus:ring-2 focus:ring-herb cursor-pointer"
      >
        {ALL_LANGUAGES.map((lang) => (
          <option
            key={lang.code}
            value={lang.code}
            disabled={!lang.active}
          >
            {lang.name} {!lang.active ? '(Coming soon)' : ''}
          </option>
        ))}
      </select>
    </div>
  );
}
