import 'package:flutter/material.dart';

class AppTheme {
  // Medical Kiosk Light Palette (Hospital-grade, accessible, high contrast)
  static const Color background = Color(0xFFF8FAFC); // Slate 50
  static const Color surface = Color(0xFFFFFFFF); // Pure White
  static const Color surfaceHighlight = Color(0xFFF1F5F9); // Slate 100
  static const Color surfaceBorder = Color(0xFFE2E8F0); // Slate 200
  static const Color surfaceBorderStrong = Color(0xFFCBD5E1); // Slate 300

  // Primary Clinical Accents
  static const Color primaryBlue = Color(0xFF0284C7); // Sky 600 - Clinical Blue
  static const Color primaryDark = Color(0xFF0369A1); // Sky 700
  static const Color accentCyan = Color(0xFF0EA5E9); // Sky 500
  static const Color tealAccent = Color(0xFF0D9488); // Teal 600 - Ayurveda & Wellness
  static const Color tealLight = Color(0xFFCCFBF1); // Teal 100

  // Status Accents
  static const Color successGreen = Color(0xFF16A34A); // Emerald 600
  static const Color successGreenBright = Color(0xFF22C55E);
  static const Color successLight = Color(0xFFDCFCE7);
  static const Color alertRed = Color(0xFFDC2626); // Red 600
  static const Color alertRedBright = Color(0xFFEF4444);
  static const Color alertLight = Color(0xFFFEE2E2);
  static const Color warningOrange = Color(0xFFD97706); // Amber 600
  static const Color warningLight = Color(0xFFFEF3C7);
  static const Color purpleAccent = Color(0xFF7C3AED); // Violet 600
  static const Color purpleLight = Color(0xFFF3E8FF);

  // High-contrast Typography for Touch Kiosks
  static const Color textPrimary = Color(0xFF0F172A); // Slate 900
  static const Color textSecondary = Color(0xFF475569); // Slate 600
  static const Color textMuted = Color(0xFF94A3B8); // Slate 400

  // Kiosk Shadows
  static const List<BoxShadow> cardShadow = [
    BoxShadow(
      color: Color(0x0A0F172A),
      blurRadius: 12,
      offset: Offset(0, 4),
    ),
    BoxShadow(
      color: Color(0x050F172A),
      blurRadius: 4,
      offset: Offset(0, 1),
    ),
  ];

  static const List<BoxShadow> elevatedCardShadow = [
    BoxShadow(
      color: Color(0x140F172A),
      blurRadius: 20,
      offset: Offset(0, 8),
    ),
    BoxShadow(
      color: Color(0x080F172A),
      blurRadius: 6,
      offset: Offset(0, 2),
    ),
  ];

  static ThemeData get lightTheme {
    return ThemeData(
      brightness: Brightness.light,
      scaffoldBackgroundColor: background,
      primaryColor: primaryBlue,
      cardColor: surface,
      canvasColor: background,
      dividerColor: surfaceBorder,
      colorScheme: const ColorScheme.light(
        primary: primaryBlue,
        secondary: accentCyan,
        surface: surface,
        error: alertRed,
        onPrimary: Colors.white,
        onSurface: textPrimary,
      ),
      fontFamily: 'Roboto',
      textTheme: const TextTheme(
        displayLarge: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: textPrimary, letterSpacing: -0.5),
        displayMedium: TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: textPrimary, letterSpacing: -0.3),
        titleLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w700, color: textPrimary),
        titleMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: textPrimary),
        bodyLarge: TextStyle(fontSize: 16, fontWeight: FontWeight.normal, color: textPrimary, height: 1.4),
        bodyMedium: TextStyle(fontSize: 14, fontWeight: FontWeight.normal, color: textSecondary, height: 1.4),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryBlue,
          foregroundColor: Colors.white,
          elevation: 2,
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 18),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold, letterSpacing: 0.3),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: textPrimary,
          side: const BorderSide(color: surfaceBorderStrong, width: 1.5),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceHighlight,
        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: surfaceBorder),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: surfaceBorder),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: primaryBlue, width: 2),
        ),
        labelStyle: const TextStyle(color: textSecondary, fontSize: 15),
        hintStyle: const TextStyle(color: textMuted, fontSize: 15),
      ),
    );
  }

  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: const Color(0xFF0B0F17),
      primaryColor: primaryBlue,
      cardColor: const Color(0xFF161B26),
      colorScheme: const ColorScheme.dark(
        primary: primaryBlue,
        secondary: accentCyan,
        surface: Color(0xFF161B26),
        error: alertRedBright,
        onPrimary: Colors.white,
        onSurface: Color(0xFFF0F6FC),
      ),
    );
  }
}
