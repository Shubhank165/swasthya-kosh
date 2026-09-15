/// Convenience accessor for the generated localizations.
///
/// One import instead of two, and one place to look up how a widget reaches a
/// string. Nothing here is a string itself — the ARB files are the only source
/// of UI text, and clinical prompts never appear in either.
library;

import 'app_localizations.dart';

typedef Strings = AppLocalizations;

/// The languages the UI is translated into — 2/3 §14.
///
/// Distinct from the languages the *question bundle* offers, which is `en` and
/// `hi` only. The app can present its own chrome in nine languages and still be
/// unable to ask a clinical question in seven of them; where that happens the
/// walker records `not_asked` rather than falling back to English.
const uiLanguages = ['en', 'hi', 'bn', 'ta', 'te', 'mr', 'gu', 'kn', 'pa'];
