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

  final FlutterSecureStorage _storage;

  Future<String?> token() => _storage.read(key: _token);
  Future<String?> patientRef() => _storage.read(key: _patientRef);

  Future<void> save({required String token, required String patientRef}) async {
    await _storage.write(key: _token, value: token);
    await _storage.write(key: _patientRef, value: patientRef);
  }

  Future<void> clear() async {
    await _storage.delete(key: _token);
    await _storage.delete(key: _patientRef);
  }
}
