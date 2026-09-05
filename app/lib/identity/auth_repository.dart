/// Sign-in — 2/3 §7.
///
/// Phone plus OTP, against the backend's `/auth/otp/*`. The token goes into
/// Keychain / Keystore via [SessionStore] and never into shared preferences.
///
/// **ABHA is never mandatory** (§7.2) and guest sign-in is a first-class path
/// (§7.3): the whole app works with a phone number alone.
library;

import 'package:dio/dio.dart';

import '../core/api.dart';
import '../core/secure_key.dart';

class OtpChallenge {
  const OtpChallenge({
    required this.challengeId,
    required this.delivery,
    this.code,
  });

  final String challengeId;

  /// `mock` or the gateway's name. Surfaced in the UI so a mocked delivery is
  /// never presented as a real SMS (§7.2's reasoning, applied to OTP).
  final String delivery;

  /// Populated only by the mock sender outside production, so a demo with no
  /// signal can complete a sign-in.
  final String? code;

  bool get isMocked => delivery == 'mock';
}

class AuthResult {
  const AuthResult({required this.ok, this.message});
  final bool ok;
  final String? message;
}

class AuthRepository {
  AuthRepository({
    required ApiClient api,
    required SessionStore sessions,
    Future<void> Function()? purgeLocalData,
  })  : _api = api,
        _sessions = sessions,
        _purge = purgeLocalData;

  final ApiClient _api;
  final SessionStore _sessions;

  /// Wipes the encrypted database — §10, "on sign-out: clear everything".
  ///
  /// Injected rather than reached for, so this class still knows nothing about
  /// storage, and so the guarantee has one home instead of being a step every
  /// caller of [signOut] has to remember.
  final Future<void> Function()? _purge;

  Future<OtpChallenge?> requestCode(String phone) async {
    final Response<Map<String, dynamic>> response;
    try {
      response = await _api.post<Map<String, dynamic>>(
        '/auth/otp/request',
        body: {'phone': phone},
      );
    } on DioException {
      // No signal, no route to the backend, DNS failure. The sign-in screen
      // shows its error and offers the button again; an exception out of here
      // would reach the framework instead, as an unhandled error on a screen
      // the patient cannot leave.
      return null;
    }
    if (response.statusCode != 201 || response.data == null) return null;
    final data = response.data!;
    return OtpChallenge(
      challengeId: data['challenge_id'] as String,
      delivery: data['delivery'] as String? ?? 'unknown',
      code: data['code'] as String?,
    );
  }

  Future<AuthResult> verify({
    required String challengeId,
    required String code,
  }) async {
    final Response<Map<String, dynamic>> response;
    try {
      response = await _api.post<Map<String, dynamic>>(
        '/auth/otp/verify',
        body: {'challenge_id': challengeId, 'code': code},
      );
    } on DioException {
      return const AuthResult(
        ok: false,
        message: 'could not reach the hospital; check your connection',
      );
    }
    if (response.statusCode != 200 || response.data == null) {
      // The backend returns one message for every failure so the endpoint is
      // not an oracle for which numbers have accounts. Passing it through
      // verbatim keeps that property in the UI.
      return AuthResult(
        ok: false,
        message: (response.data?['message'] as String?) ??
            'that code is not valid; request a new one',
      );
    }
    await _sessions.save(
      token: response.data!['token'] as String,
      patientRef: response.data!['patient_ref'] as String,
    );
    return const AuthResult(ok: true);
  }

  Future<bool> isSignedIn() async => (await _sessions.token()) != null;

  /// Sign in without a screen, for walking the app during development.
  ///
  /// Configured by `--dart-define=MEDIKIOSK_DEV_SIGN_IN=<phone>` and off in
  /// every build that does not pass it.
  ///
  /// **It cannot work against a real deployment.** It reads the OTP out of the
  /// request response, which only the mock sender populates and which the
  /// backend refuses to populate in production — so against anything real there
  /// is no code to submit and this returns false, leaving the ordinary sign-in
  /// screen exactly as it was. That is a property of the mechanism, not a
  /// promise about how carefully it is used.
  Future<bool> devSignIn(String phone) async {
    try {
      if (await isSignedIn()) return true;
      final challenge = await requestCode(phone);
      final code = challenge?.code;
      if (challenge == null || code == null) return false;
      final result = await verify(challengeId: challenge.challengeId, code: code);
      return result.ok;
    } on Object {
      // A shortcut that cannot reach the backend is a shortcut that does not
      // happen. It must never become a failure the patient — or the developer
      // holding the phone — has to get past.
      return false;
    }
  }

  /// Sign out.
  ///
  /// Revokes server-side, then clears local state — **and clears local state
  /// even if the server call fails**. §10 requires the device to be wiped on
  /// sign-out, and a patient on a borrowed phone with no signal must still be
  /// able to leave nothing behind.
  ///
  /// "Local state" is the session **and the database**: drafts, queued records,
  /// captured pages and receipts. Clearing the token alone would leave a
  /// stranger's health answers on the phone behind a screen that merely looks
  /// signed out.
  ///
  /// The purge runs before the token is dropped, because it is the token the
  /// next holder must not have; and it runs even if it throws, because a
  /// half-cleared device must not also be a signed-in one.
  Future<void> signOut() async {
    try {
      await _api.post<void>('/auth/otp/sign-out');
    } on Object {
      // Deliberately ignored. See above.
    }
    try {
      await _purge?.call();
    } finally {
      await _sessions.clear();
    }
  }
}
