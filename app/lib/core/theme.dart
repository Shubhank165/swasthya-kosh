/// Visual design — 2/3 §14.
///
/// The accessibility numbers here are requirements, not preferences. This app's
/// users include elderly patients in an OPD waiting room, people reading a
/// second language, and relatives filling a form for someone else on a cracked
/// phone in poor light.
///
/// - **18sp minimum body text**, and the OS text-scale setting respected up to
///   200% without breaking layout.
/// - **48dp minimum touch targets.**
/// - **WCAG AA contrast** on every text-on-background pair below.
///
/// The colour choices are deliberately low-chroma. This is a clinical intake
/// form, and a saturated palette reads as a consumer app — which is the wrong
/// signal for something whose output a physician relies on.
library;

import 'package:flutter/material.dart';

abstract final class Sizes {
  /// §14. Below this, nothing.
  static const double minTouchTarget = 48;
  static const double bodyText = 18;
  static const double promptText = 24;
  static const double gutter = 20;
  static const double gap = 12;

  /// The cap on OS text scaling. Beyond 2.0 a one-question-per-screen layout
  /// still works, but the answer options stop fitting without scrolling in a
  /// way that hides the "I don't know" affordance below the fold — and that
  /// affordance disappearing is a clinical problem, not a cosmetic one.
  static const double maxTextScale = 2.0;
}

abstract final class Palette {
  static const seed = Color(0xFF1B5E4A);
  static const surface = Color(0xFFFCFCFA);

  /// The urgent-care screen only (§6). Used nowhere else, so its appearance is
  /// unambiguous.
  static const urgent = Color(0xFFB3261E);
  static const urgentSurface = Color(0xFFFFF6F5);
}

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: Palette.seed,
    surface: Palette.surface,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    textTheme: const TextTheme(
      bodyLarge: TextStyle(fontSize: Sizes.bodyText, height: 1.5),
      bodyMedium: TextStyle(fontSize: Sizes.bodyText, height: 1.5),
      titleLarge: TextStyle(
        fontSize: Sizes.promptText,
        height: 1.4,
        fontWeight: FontWeight.w600,
      ),
      labelLarge: TextStyle(fontSize: Sizes.bodyText, fontWeight: FontWeight.w600),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(56),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        textStyle: const TextStyle(fontSize: Sizes.bodyText, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(56),
        textStyle: const TextStyle(fontSize: Sizes.bodyText),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(Sizes.minTouchTarget, Sizes.minTouchTarget),
        textStyle: const TextStyle(fontSize: Sizes.bodyText),
      ),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      border: OutlineInputBorder(),
      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 20),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
  );
}

/// Clamp the OS text scale.
///
/// Respecting the setting is the requirement; respecting it without bound means
/// a 300% scale pushes the "I don't know" button off screen. Clamped at the top
/// only — a patient who has made text *smaller* is not creating a safety
/// problem.
Widget withClampedTextScale(BuildContext context, Widget child) {
  final media = MediaQuery.of(context);
  return MediaQuery(
    data: media.copyWith(
      textScaler: media.textScaler.clamp(maxScaleFactor: Sizes.maxTextScale),
    ),
    child: child,
  );
}
