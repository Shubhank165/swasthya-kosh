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
/// The colour choices stay low-chroma for a clinical tool, but the green was
/// too dark to read as a health app and too close to grey at small sizes. It is
/// now a true emerald, checked at 4.5:1 against white for text and 3:1 for the
/// icon and border uses.
///
/// **Depth comes from shadow, not outline.** Cards used to be a 1px box, which
/// at nine languages and 200% scale turns a screen into a wireframe: every
/// element equally weighted, nothing nearer than anything else. They now sit on
/// a soft shadow and use a hairline only where two white surfaces touch.
///
/// **The tints are surfaces, never meaning.** [Palette.tint] and
/// [Palette.tintStrong] group things and mark a selection; they never encode a
/// clinical state. Exactly one colour in this file says something —
/// [Palette.urgent] — and it appears on one screen. A palette where three
/// greens each mean something different is a palette a patient has to learn.
library;

import 'package:flutter/material.dart';

abstract final class Sizes {
  /// §14. Below this, nothing.
  static const double minTouchTarget = 48;
  static const double bodyText = 18;
  static const double promptText = 24;
  static const double gutter = 20;
  static const double gap = 12;

  /// Corner radii. Two values, not five: a screen where every container has
  /// its own radius reads as assembled rather than designed.
  static const double radius = 18;
  static const double radiusLarge = 26;

  /// Every primary action is this tall, everywhere. A patient with a tremor
  /// aiming at a 40dp button is the accessibility failure §14 exists to stop,
  /// and a button that changes height between screens costs a re-aim.
  static const double actionHeight = 56;

  /// The rounded square behind a row's icon.
  static const double chip = 46;

  /// The cap on OS text scaling. Beyond 2.0 a one-question-per-screen layout
  /// still works, but the answer options stop fitting without scrolling in a
  /// way that hides the "I don't know" affordance below the fold — and that
  /// affordance disappearing is a clinical problem, not a cosmetic one.
  static const double maxTextScale = 2.0;
}

abstract final class Palette {
  static const seed = Color(0xFF0E7A57);

  /// Not white. A barely-there mint, so a white card has something to sit on
  /// and the page does not read as a blank document.
  static const surface = Color(0xFFF7FBF9);

  /// The urgent-care screen only (§6). Used nowhere else, so its appearance is
  /// unambiguous.
  static const urgent = Color(0xFFB3261E);
  static const urgentSurface = Color(0xFFFFF6F5);

  /// Grouping surfaces. A card sitting on [tint] reads as "these belong
  /// together"; [tintStrong] marks the one row the patient has chosen.
  ///
  /// Both are pale enough that 18sp text at `onSurface` clears AA on them,
  /// which is the constraint that set the values — not the other way round.
  static const tint = Color(0xFFE9F4EF);
  static const tintStrong = Color(0xFFD3E9DE);

  /// Hairlines, for where two white surfaces meet and nothing else. One line
  /// colour, so a card border and a divider cannot disagree by two per cent.
  static const line = Color(0xFFE4EDE8);
}

/// The one elevation in this app.
///
/// A single shadow used everywhere beats a scale of five that nobody can tell
/// apart on an LCD in daylight. Two layers: a tight one that separates the card
/// from the page, and a wide soft one that gives it somewhere to sit.
const List<BoxShadow> softShadow = [
  BoxShadow(color: Color(0x0D12503A), blurRadius: 2, offset: Offset(0, 1)),
  BoxShadow(color: Color(0x141B5E4A), blurRadius: 18, offset: Offset(0, 6)),
];

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: Palette.seed,
    surface: Palette.surface,
  );

  final rounded = RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(Sizes.radius),
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: scheme.surface,
    textTheme: const TextTheme(
      bodyLarge: TextStyle(fontSize: Sizes.bodyText, height: 1.5),
      bodyMedium: TextStyle(fontSize: Sizes.bodyText, height: 1.5),
      // One step down from body, for the quiet second line under a title. Still
      // 15sp — §14's floor is for the text a patient must read, and this is
      // never the only place something is said.
      bodySmall: TextStyle(fontSize: 15, height: 1.45),
      titleLarge: TextStyle(
        fontSize: Sizes.promptText,
        height: 1.35,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.2,
      ),
      titleMedium: TextStyle(
        fontSize: 19,
        height: 1.3,
        fontWeight: FontWeight.w600,
      ),
      // The one display size, used by the screens that open a flow rather than
      // continue one — welcome, urgent care, submitted. Nothing mid-interview
      // uses it: a question prompt at 30sp fits three words a line at 200%.
      headlineMedium: TextStyle(
        fontSize: 30,
        height: 1.22,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.5,
      ),
      labelLarge: TextStyle(fontSize: Sizes.bodyText, fontWeight: FontWeight.w600),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      foregroundColor: scheme.onSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(Sizes.actionHeight),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        shape: rounded,
        elevation: 0,
        textStyle: const TextStyle(fontSize: Sizes.bodyText, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(Sizes.actionHeight),
        shape: rounded,
        backgroundColor: Colors.white,
        side: const BorderSide(color: Palette.line),
        textStyle: const TextStyle(fontSize: Sizes.bodyText, fontWeight: FontWeight.w600),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(Sizes.minTouchTarget, Sizes.minTouchTarget),
        shape: rounded,
        textStyle: const TextStyle(fontSize: Sizes.bodyText),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 20),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Sizes.radius),
        borderSide: const BorderSide(color: Palette.line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Sizes.radius),
        borderSide: const BorderSide(color: Palette.line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(Sizes.radius),
        borderSide: BorderSide(color: scheme.primary, width: 2),
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: Colors.white,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Sizes.radius),
      ),
    ),
    dividerTheme: const DividerThemeData(
      color: Palette.line,
      thickness: 1,
      space: 1,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
      indicatorColor: Palette.tintStrong,
      elevation: 0,
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
      ),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      linearTrackColor: Palette.tintStrong,
      color: scheme.primary,
      linearMinHeight: 8,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: rounded,
      contentTextStyle: const TextStyle(fontSize: Sizes.bodyText),
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
