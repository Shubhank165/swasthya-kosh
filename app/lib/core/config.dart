/// Runtime configuration — 2/3 §13.
///
/// No hostname, key or token literal in this file or anywhere else in the app,
/// for the same reason the backend has none: this repository is shared under
/// deadline pressure, and a credential committed once is a credential leaked
/// forever. The base URL comes from `--dart-define` at build time.
library;

class AppConfig {
  const AppConfig({
    required this.baseUrl,
    required this.appVersion,
    this.emergencyNumber = '108',
    this.devSignInPhone = '',
  });

  /// `flutter run --dart-define=MEDIKIOSK_BASE_URL=http://10.0.2.2:8000`
  ///
  /// `10.0.2.2` is the host machine from inside the Android emulator, which is
  /// the local-backend default §15 item 2 tests against.
  factory AppConfig.fromEnvironment() => const AppConfig(
        baseUrl: String.fromEnvironment(
          'MEDIKIOSK_BASE_URL',
          defaultValue: 'http://10.0.2.2:8000',
        ),
        appVersion: String.fromEnvironment('APP_VERSION', defaultValue: '1.0.0'),
        devSignInPhone: String.fromEnvironment('MEDIKIOSK_DEV_SIGN_IN'),
      );

  final String baseUrl;
  final String appVersion;

  /// A phone number to sign in as automatically, for walking the app without
  /// typing a number and a code at every launch.
  ///
  /// ```
  /// flutter run --dart-define=MEDIKIOSK_DEV_SIGN_IN=+919812345678
  /// ```
  ///
  /// **It cannot work against a real deployment**, and that is a property of
  /// the mechanism rather than a promise: it signs in by reading the OTP out of
  /// the request response, which only the mock sender populates and which
  /// `PatientAuthService` refuses to populate in production. Against anything
  /// real it finds no code and gives up, leaving the ordinary sign-in screen.
  ///
  /// Empty in every build that does not pass the define, which is all of them
  /// unless somebody typed it.
  final String devSignInPhone;

  bool get autoSignIn => devSignInPhone.isNotEmpty;

  /// The ambulance number shown on the urgent-care screen.
  ///
  /// **108 is the default and is not universal.** It is the common ambulance
  /// number across most Indian states but not all, so a hospital whose region
  /// differs must be able to change it without an app release — which is why
  /// this reads from the hospital record when one is loaded rather than being
  /// a constant in the urgent-care widget. `2/3 §6` flags this for clinician
  /// confirmation before shipping.
  final String emergencyNumber;

  AppConfig withEmergencyNumber(String? number) =>
      number == null || number.isEmpty
          ? this
          : AppConfig(
              baseUrl: baseUrl,
              appVersion: appVersion,
              emergencyNumber: number,
              devSignInPhone: devSignInPhone,
            );
}
