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

/// The hospital the patient last chose, remembered between launches.
///
/// The Visits, Documents and Profile tabs read `GET /patients/me/*`, which the
/// backend scopes to one hospital and refuses without an `X-Hospital-Id`
/// header. Outside an intake there is no hospital picker on screen, so without
/// this the header is absent, the call is a 401, and the tabs render empty for
/// a patient who does have a history. Cleared on sign-out with everything else.
class HospitalStore {
  HospitalStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  static const _key = 'medikiosk.session.hospital_id';

  final FlutterSecureStorage _storage;

  Future<String?> read() async {
    try {
      return await _storage.read(key: _key);
    } on Object {
      return null;
    }
  }

  Future<void> write(String hospitalId) async {
    try {
      await _storage.write(key: _key, value: hospitalId);
    } on Object {/* best effort — an auto-select still covers a single-site app */}
  }

  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } on Object {/* nothing to clear */}
  }
}

/// Whether questions are read aloud automatically, remembered between launches.
///
/// Read-aloud starts on its own when a question opens (§14) so a patient who
/// chose a script they cannot read is not asked to reach for a button on every
/// screen. The speaker control then becomes a mute toggle, and this is where
/// that choice is kept so it survives a restart. It is an accessibility
/// preference, not patient data, so unlike the language and hospital it is
/// **not** cleared on sign-out — the next patient on a shared phone keeps the
/// same accommodation until they turn it off themselves.
class ReadAloudPrefStore {
  ReadAloudPrefStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  static const _key = 'medikiosk.ui.read_aloud';

  final FlutterSecureStorage _storage;

  /// `null` when the patient has never changed it — the caller then keeps the
  /// on-by-default behaviour.
  Future<bool?> read() async {
    try {
      final raw = await _storage.read(key: _key);
      if (raw == null) return null;
      return raw == 'true';
    } on Object {
      return null;
    }
  }

  Future<void> write(bool enabled) async {
    try {
      await _storage.write(key: _key, value: enabled ? 'true' : 'false');
    } on Object {/* best effort */}
  }
}


/// Whether the first-run demo has been shown, on this device and nowhere
/// else — see `home/onboarding_demo_screen.dart`.
///
/// Deliberately its own flag rather than reusing "a language has been
/// stored" the way the welcome screen does. The demo sits between Welcome and
/// Language, and a patient who backs out of it partway through, or who signs
/// out and back in, must still not be shown it a second time — the flag has
/// to survive both, which "no language chosen yet" and "no session" do not.
///
/// Like [ReadAloudPrefStore], this is a device preference, not patient data:
/// it is **not** cleared on sign-out. A demo shown once on a shared kiosk
/// phone has done its job for every patient who picks that phone up next.
class OnboardingStore {
  OnboardingStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  static const _key = 'medikiosk.ui.onboarding_seen';

  final FlutterSecureStorage _storage;

  /// `false` for a genuine first run and for a keystore that could not be
  /// read — an unreadable preference must fail toward showing the demo once
  /// more, never toward silently skipping it forever.
  Future<bool> read() async {
    try {
      return await _storage.read(key: _key) == 'true';
    } on Object {
      return false;
    }
  }

  Future<void> markSeen() async {
    try {
      await _storage.write(key: _key, value: 'true');
    } on Object {/* best effort — worst case the demo shows again */}
  }
}

/// What the patient would like to be called, on this device and nowhere else.
///
/// **The backend has no name column and this does not give it one.** §7.1 holds
/// a peppered HMAC of a phone number and nothing else; `PatientRecord` has no
/// `display_name` the app can write to, and `profile_tab.dart` says out loud
/// that a profile screen which looks like it should hold a name is an
/// invitation to start collecting them. So this is a greeting, not an
/// identifier: it is never sent, never submitted with an intake, never used to
/// match a patient, and it is cleared on sign-out with everything else.
///
/// A patient who sets nothing gets a greeting without a name, which is the
/// default and is fine. Nothing anywhere invents one.
class DisplayNameStore {
  DisplayNameStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  static const _key = 'medikiosk.session.display_name';

  final FlutterSecureStorage _storage;

  Future<String?> read() async {
    try {
      final value = await _storage.read(key: _key);
      final trimmed = value?.trim();
      return (trimmed == null || trimmed.isEmpty) ? null : trimmed;
    } on Object {
      return null;
    }
  }

  Future<void> write(String name) async {
    final trimmed = name.trim();
    try {
      if (trimmed.isEmpty) {
        await _storage.delete(key: _key);
      } else {
        await _storage.write(key: _key, value: trimmed);
      }
    } on Object {/* best effort — a greeting is not worth failing a screen */}
  }

  Future<void> clear() async {
    try {
      await _storage.delete(key: _key);
    } on Object {/* nothing to clear */}
  }
}
