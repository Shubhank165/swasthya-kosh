/// The database encryption key — 2/3 §10.
///
/// Health answers, drafts and queued submissions live in SQLite. That file sits
/// in app-private storage, which is not a meaningful protection on a rooted
/// phone or against an offline image of the device — so the database is
/// encrypted, and the key lives in the platform keystore rather than beside it.
///
/// The key is generated once on first launch and never leaves
/// Keychain / Keystore. It is never written to the database, never to shared
/// preferences, and never logged.
library;

import 'dart:convert';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class DatabaseKey {
  DatabaseKey({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
            );

  static const _keyName = 'medikiosk.db.key';
  final FlutterSecureStorage _storage;

  /// The key, creating one on first use.
  Future<String> obtain() async {
    final existing = await _storage.read(key: _keyName);
    if (existing != null && existing.isNotEmpty) return existing;

    // 256 bits from the platform's secure random. `Random.secure()` is backed
    // by the OS CSPRNG; `Random()` is not, and would make the key predictable
    // from the launch time.
    final random = Random.secure();
    final bytes = List<int>.generate(32, (_) => random.nextInt(256));
    final key = base64UrlEncode(bytes);
    await _storage.write(key: _keyName, value: key);
    return key;
  }

  /// Destroy the key.
  ///
  /// On sign-out (§10) this is what makes the local database unreadable even if
  /// the file survives deletion — which it may, since deleting a file does not
  /// erase its blocks.
  Future<void> destroy() => _storage.delete(key: _keyName);
}

/// The patient's session token — 2/3 §7.1.
///
/// Keychain / Keystore, never shared preferences.
class SessionStore {
  SessionStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  static const _token = 'medikiosk.session.token';
  static const _patientRef = 'medikiosk.session.patient_ref';

  /// The number the patient signed in with, for the profile screen to show.
  ///
  /// The backend cannot supply this: what it stores is a peppered HMAC of the
  /// number (§7.1) and a digest does not come back as digits. So the only copy
  /// is this one, on the patient's own device, in the platform keystore, and
  /// cleared by [clear] along with everything else on sign-out.
  static const _phone = 'medikiosk.session.phone';

  final FlutterSecureStorage _storage;

  Future<String?> token() => _storage.read(key: _token);
  Future<String?> patientRef() => _storage.read(key: _patientRef);
  Future<String?> phone() => _storage.read(key: _phone);

  Future<void> save({
    required String token,
    required String patientRef,
    String? phone,
  }) async {
    await _storage.write(key: _token, value: token);
    await _storage.write(key: _patientRef, value: patientRef);
    if (phone != null) await _storage.write(key: _phone, value: phone);
  }

  Future<void> clear() async {
    await _storage.delete(key: _token);
    await _storage.delete(key: _patientRef);
    await _storage.delete(key: _phone);
  }
}

/// The language the patient chose, remembered between launches.
///
/// **Not a secret, and stored here anyway.** This is the only durable
/// key-value store the app already carries — §7.1 and §10 keep the database key
/// and the session token out of shared preferences, so shared preferences is
/// not a dependency at all, and adding one to remember a two-letter language
/// code is not worth it.
///
/// It is why the chooser stopped being a screen you see on every launch:
/// `languageProvider` defaulted to `en` in memory and forgot the answer the
/// moment the process died, so the first thing the app ever asked was a
/// question it had already been told.
///
/// Cleared on sign-out with everything else. A patient handing the phone back
/// leaves nothing behind, and that includes which language they read.
class LanguageStore {
  LanguageStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  static const _key = 'medikiosk.ui.language';

  final FlutterSecureStorage _storage;

  /// `null` when the patient has never chosen — which is what the first-run
  /// chooser tests, rather than comparing against a default that is also a
  /// legitimate answer.
  Future<String?> read() async {
    try {
      return await _storage.read(key: _key);
    } on Object {
      // A locked keystore or a platform channel that is not there yet. An
      // unreadable preference is a first run, not a crash on launch.
      return null;
    }
  }

  Future<void> write(String language) async {
    try {
      await _storage.write(key: _key, value: language);
    } on Object {
      // Best effort. Failing to remember the language is not a reason to stop
      // the patient using the app in it.
    }
  }

  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } on Object {/* nothing to clear */}
  }
}
