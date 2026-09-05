/// Riverpod wiring — 2/3 §13.
///
/// One place where objects are constructed, so "what is this app actually
/// running" is answerable by reading a single file — the same reasoning as the
/// backend's `adapters/registry.py`.
library;

import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../consent/consent_repository.dart';
import '../content/bundle.dart';
import '../content/bundle_repository.dart';
import '../documents/document_store.dart';
import '../identity/abha_repository.dart';
import '../identity/auth_repository.dart';
import '../identity/history_repository.dart';
import '../identity/hospital_repository.dart';
import '../storage/database.dart';
import '../submit/queue.dart';
import 'api.dart';
import 'config.dart';
import 'secure_key.dart';

final configProvider = Provider<AppConfig>((ref) => AppConfig.fromEnvironment());

final sessionStoreProvider = Provider<SessionStore>((ref) => SessionStore());

final databaseKeyProvider = Provider<DatabaseKey>((ref) => DatabaseKey());

final apiProvider = Provider<ApiClient>((ref) {
  final sessions = ref.watch(sessionStoreProvider);
  return ApiClient(
    config: ref.watch(configProvider),
    readToken: sessions.token,
    // Read, not watched: the header has to be whatever is selected when the
    // request goes out, and rebuilding the client on every hospital tap would
    // throw away its connection pool for nothing.
    readHospitalId: () => ref.read(selectedHospitalProvider)?.id,
  );
});

final authProvider = Provider<AuthRepository>((ref) => AuthRepository(
      api: ref.watch(apiProvider),
      sessions: ref.watch(sessionStoreProvider),
      // §10: sign-out clears everything, not just the token. A database that
      // has never been opened has nothing to clear, which is why this tolerates
      // the provider failing rather than refusing to sign the patient out.
      purgeLocalData: () async {
        try {
          final database = await ref.read(databaseProvider.future);
          await database.purgeEverything();
        } on Object {
          return;
        }
      },
    ));

final hospitalRepositoryProvider = Provider<HospitalRepository>(
  (ref) => HospitalRepository(api: ref.watch(apiProvider)),
);

final bundleRepositoryProvider = Provider<BundleRepository>(
  (ref) => BundleRepository(api: ref.watch(apiProvider)),
);

final consentRepositoryProvider = Provider<ConsentRepository>(
  (ref) => ConsentRepository(api: ref.watch(apiProvider)),
);

final abhaRepositoryProvider = Provider<AbhaRepository>(
  (ref) => AbhaRepository(api: ref.watch(apiProvider)),
);

final historyRepositoryProvider = Provider<HistoryRepository>(
  (ref) => HistoryRepository(api: ref.watch(apiProvider)),
);

/// What this hospital already holds about the signed-in patient — §5 screen 5.
/// Empty for a guest and empty on any failure; it must never block an intake.
final carryForwardProvider = FutureProvider<List<CarriedFact>>(
  (ref) => ref.watch(historyRepositoryProvider).carryForward(),
);

/// Where captured pages live before they upload.
///
/// A subdirectory of application documents rather than a cache directory: the
/// OS may evict a cache at any moment, and evicting a prescription photograph
/// between capture and upload would lose it silently.
final documentStoreProvider = FutureProvider<DocumentStore>((ref) async {
  final documents = await getApplicationDocumentsDirectory();
  return DocumentStore(
    database: await ref.watch(databaseProvider.future),
    directory: Directory(p.join(documents.path, 'pages')),
  );
});

/// The local database, opened once with the key from the platform keystore.
final databaseProvider = FutureProvider<LocalDatabase>((ref) async {
  final key = await ref.watch(databaseKeyProvider).obtain();
  final database = await LocalDatabase.open(encryptionKey: key);
  ref.onDispose(database.close);
  return database;
});

/// The submission queue — §9. One per app, so a launch-time flush and a
/// patient tapping send share the in-flight guard rather than racing.
final submissionQueueProvider = FutureProvider<SubmissionQueue>((ref) async {
  return SubmissionQueue(
    database: await ref.watch(databaseProvider.future),
    api: ref.watch(apiProvider),
  );
});

/// The consent notice for **this** surface — `source=app`, which omits the
/// kiosk's audio-retention purpose because this app has no microphone (§11).
final consentNoticeProvider = FutureProvider<ConsentNotice?>(
  (ref) => ref.watch(consentRepositoryProvider).load(),
);

/// What the patient granted, held between the consent screen and the intake it
/// is filed against.
final consentGrantProvider = StateProvider<ConsentGrant?>((ref) => null);

/// The question bundle, refreshed on launch and served from cache when offline.
final bundleProvider = FutureProvider<BundleFetchResult?>(
  (ref) => ref.watch(bundleRepositoryProvider).load(),
);

final hospitalsProvider = FutureProvider<List<Hospital>>(
  (ref) => ref.watch(hospitalRepositoryProvider).list(),
);

/// An interrupted intake worth offering to resume — §5, §15 item 7.
///
/// Excludes a draft that already has an assembled payload: that one is not
/// interrupted, it is submitted and waiting for signal, and offering to
/// "continue" it would let the patient edit answers the hospital may already
/// have.
final resumableDraftProvider = FutureProvider<Draft?>((ref) async {
  final database = await ref.watch(databaseProvider.future);
  final draft = await database.latestDraft();
  if (draft == null || draft.queuedPayload != null) return null;
  return draft;
});

/// How old a draft may be before the patient is asked to start again — §5.
///
/// Clinical answers go stale. "How long have you had this pain?" answered last
/// week is wrong today, and submitting it quietly would be worse than asking
/// again.
const draftMaxAge = Duration(days: 7);

/// Whether a session token is present.
///
/// With `MEDIKIOSK_DEV_SIGN_IN` set this signs in first, so a developer walking
/// the app is not typing a number and a code at every launch. The define is
/// absent in every ordinary build, and the mechanism cannot work against a real
/// backend — see [AuthRepository.devSignIn].
final signedInProvider = FutureProvider<bool>((ref) async {
  final auth = ref.watch(authProvider);
  final config = ref.watch(configProvider);
  if (config.autoSignIn && !await auth.isSignedIn()) {
    await auth.devSignIn(config.devSignInPhone);
  }
  return auth.isSignedIn();
});

/// The language the patient chose.
///
/// Drives both the app's own chrome and which prompt the walker reads. They can
/// differ in coverage — the UI speaks nine languages and the bundle two — and
/// where the bundle has no prompt the walker records `not_asked` rather than
/// falling back.
final languageProvider = StateProvider<String>((ref) => 'en');

/// The hospital the patient picked (§5 screen 2).
final selectedHospitalProvider = StateProvider<Hospital?>((ref) => null);

final selectedDepartmentProvider = StateProvider<String?>((ref) => null);

/// Who the intake is about (§5 screen 4).
final reporterProvider = StateProvider<String>((ref) => 'self');

/// Who granted consent, which is not always who the intake is about (§11).
final grantingPartyProvider = StateProvider<String>((ref) => 'self');

/// Convenience: the bundle itself, or null while loading or unavailable.
final currentBundleProvider = Provider<ContentBundle?>(
  (ref) => ref.watch(bundleProvider).valueOrNull?.bundle,
);
