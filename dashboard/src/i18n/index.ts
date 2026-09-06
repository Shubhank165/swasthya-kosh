/**
 * The translation hook — 3/3 §9.
 *
 * Kept deliberately small: a locale in the session store, a lookup, and
 * `{placeholder}` substitution. No pluralisation engine, because the two
 * languages here need one rule between them and English's is `(s)`; no lazy
 * loading, because both catalogues together are a few kilobytes and a doctor
 * switching language mid-consultation should not wait for a network round trip.
 *
 * **Only the chrome.** Nothing routed through here touches a fact, a report
 * line, a marker, an alert label or a criterion — those arrive from the backend
 * in the language the interview happened in, and the locale chosen here does not
 * change what is requested. See the note at the top of `strings.ts`.
 */
import { create } from 'zustand';

import { LOCALES, STRINGS, type Locale, type StringKey } from './strings';

export { LOCALES, LOCALE_NAMES, type Locale, type StringKey } from './strings';

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

/** The browser's preference, when it is one this dashboard has. */
function initialLocale(): Locale {
  const preferred =
    typeof navigator === 'undefined' ? [] : navigator.languages ?? [navigator.language];
  for (const tag of preferred) {
    const base = String(tag).split('-')[0] as Locale;
    if ((LOCALES as readonly string[]).includes(base)) return base;
  }
  return 'en';
}

/**
 * In memory, like everything else on this screen.
 *
 * `localStorage` would be the obvious home for a UI preference and is banned
 * here — by §12, and by a lint rule. A shared OPD terminal is the reason: a
 * preference that survives the tab being closed is a preference the next person
 * to sit down inherits, and once one thing is persisted the next thing is
 * easier to persist.
 */
export const useLocale = create<LocaleState>((set) => ({
  locale: initialLocale(),
  setLocale: (locale) => set({ locale }),
}));

export type Translate = (
  key: StringKey,
  values?: Record<string, string | number>,
) => string;

export function translate(
  locale: Locale,
  key: StringKey,
  values?: Record<string, string | number>,
): string {
  // The catalogue is typed as complete, so a miss here means a key was built at
  // runtime — which nothing does, and which would be a bug worth seeing rather
  // than a blank space on a clinical screen.
  const template = STRINGS[locale][key] ?? STRINGS.en[key] ?? key;
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in values ? String(values[name]) : whole,
  );
}

export function useT(): Translate {
  const locale = useLocale((state) => state.locale);
  return (key, values) => translate(locale, key, values);
}

/** For `lang` attributes and `toLocaleString`. */
export function useLocaleTag(): string {
  return useLocale((state) => state.locale);
}
