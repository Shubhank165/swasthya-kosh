/// The screens in sequence — 2/3 §5, §15 item 1.
///
/// Every widget test under `test/` renders one screen with callbacks wired to
/// nothing. This one starts at the language chooser and taps all the way to a
/// reference code, through the real providers with fake edges, so the *order*
/// of §5 is asserted rather than assumed — "every screen works and the sequence
/// is wrong" is a failure no per-screen test can see.
///
/// **It lives here rather than under `test/` because it cannot run on the
/// host.** `testWidgets` drives a fake clock, and the encrypted database's
/// queries complete on real async work that the fake clock never advances: the
/// test does not fail, it hangs. An integration test runs against a real
/// binding on a device, where both are real.
///
/// ```
/// flutter test integration_test/journey_test.dart      # needs a device
/// ```
///
/// **Status: executed, and it passes.** Run on a physical Android device
/// (OnePlus CPH2381, Android 14) — 3/3 §B2.
///
/// Running it found what a host test structurally could not: `LocalDatabase
/// .memory()` opened a connection without first pointing sqlite3 at the
/// SQLCipher build, and this app ships SQLCipher and deliberately not
/// `sqlite3_flutter_libs` beside it. On a host the system SQLite is there and
/// the omission is invisible; on a device there is no `libsqlite3.so` and the
/// first query threw before a screen rendered. Every lower-level test passed
/// throughout.
///
/// Everything it asserts is also asserted somewhere else at a lower level — the
/// flow controller in `test/flow_test.dart`, each screen in
/// `test/screens_test.dart`. What it adds is the seam between them, and the
/// device underneath.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:medikiosk_app/consent/consent_repository.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/content/bundle_repository.dart';
import 'package:medikiosk_app/core/providers.dart';
import 'package:medikiosk_app/documents/document_store.dart';
import 'package:medikiosk_app/identity/hospital_repository.dart';
import 'package:medikiosk_app/main.dart';
import 'package:medikiosk_app/storage/database.dart';
import 'package:medikiosk_app/submit/queue.dart';

import '../test/bundle_fixture.dart';
import '../test/fake_api.dart';

ContentBundle journeyBundle() => bundleWith(
      questions: [
        question(
          'complaint',
          field: 'chief_complaint',
          type: 'single_choice',
          options: ['fever'],
          section: 'chief_complaint',
        ),
        question('duration', type: 'yes_no_unknown'),
      ],
      core: ['complaint'],
      branches: {'fever': ['duration']},
    );

const notice = ConsentNotice(
  version: '1',
  purposes: [
    ConsentPurposeSpec(
      code: 'history_intake',
      required: true,
      label: {'en': 'Recording your health history'},
      description: {'en': 'So the doctor has it before you go in.'},
    ),
  ],
);

/// Pump a bounded number of frames.
///
/// Deliberately not `pumpAndSettle`: several screens show a
/// `CircularProgressIndicator` while a provider resolves, and an indefinite
/// animation means "settled" never arrives — the test hangs rather than fails,
/// which is the worse of the two.
Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 25; i++) {
    await tester.pump(const Duration(milliseconds: 40));
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  late LocalDatabase db;
  late FakeBackend backend;
  late Directory scratch;

  setUp(() {
    db = LocalDatabase.memory();
    backend = FakeBackend();
    scratch = Directory.systemTemp.createTempSync('medikiosk_journey');
  });

  tearDown(() async {
    await db.close();
    if (scratch.existsSync()) scratch.deleteSync(recursive: true);
  });

  List<Override> edges() => [
        databaseProvider.overrideWith((ref) async => db),
        apiProvider.overrideWithValue(fakeApi(backend)),
        submissionQueueProvider.overrideWith(
          (ref) async => SubmissionQueue(database: db, api: fakeApi(backend)),
        ),
        documentStoreProvider.overrideWith(
          (ref) async => DocumentStore(database: db, directory: scratch),
        ),
        bundleProvider.overrideWith(
          (ref) async => BundleFetchResult(bundle: journeyBundle(), fromCache: false),
        ),
        hospitalsProvider.overrideWith((ref) async => [
              const Hospital(
                id: 'aiia-delhi',
                displayName: 'All India Institute of Ayurveda',
                timezone: 'Asia/Kolkata',
                defaultLanguage: 'en',
                departments: [Department(code: 'opd', display: 'General OPD')],
              ),
            ]),
        // Signed in, and a first visit: nothing is held about this patient, so
        // screen 5 has nothing to confirm and is skipped.
        signedInProvider.overrideWith((ref) async => true),
        carryForwardProvider.overrideWith((ref) async => []),
        consentNoticeProvider.overrideWith((ref) async => notice),
      ];


  testWidgets('language to reference code, in §5 order', (tester) async {
    // A phone-shaped surface, tall enough that the nine-language chooser and
    // the button under it are both on screen. The default 800x600 test window
    // is not a shape this app is ever rendered at.
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(ProviderScope(overrides: edges(), child: const MediKioskApp()));
    await settle(tester);

    // 1. Language, before anything else is shown.
    await tester.tap(find.byKey(const Key('language.en')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('start.continue')));
    await settle(tester);

    // 2. Hospital, then department. Continue appears only once both are picked.
    expect(find.byKey(const Key('hospital.continue')), findsNothing);
    await tester.tap(find.byKey(const Key('hospital.aiia-delhi')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('department.opd')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('hospital.continue')));
    await settle(tester);

    // ABHA, offered and declined. §7.2: never mandatory.
    await tester.tap(find.byKey(const Key('abha.skip')));
    await settle(tester);

    // 3. Consent — before anything clinical is collected. The required purpose
    // starts unticked, so granting is an action rather than a dismissal.
    await tester.tap(find.byKey(const Key('consent.switch.history_intake')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('consent.continue')));
    await settle(tester);

    // 4. Who is this for.
    await tester.tap(find.byKey(const Key('reporter.self')));
    await settle(tester);

    // 5 is skipped: nothing is held about this patient. 6, the complaint grid.
    await tester.tap(find.byKey(const Key('complaint.fever')));
    await settle(tester);

    // 7, the interview.
    await tester.tap(find.byKey(const Key('option.no')));
    await settle(tester);

    // 9, documents — after the interview, before the review.
    expect(find.byKey(const Key('documents.continue')), findsOneWidget);
    await tester.tap(find.byKey(const Key('documents.continue')));
    await settle(tester);

    // 10, review, then 11, the code.
    await tester.tap(find.byKey(const Key('review.submit')));
    await settle(tester);

    expect(find.byKey(const Key('submitted.code')), findsOneWidget);
    expect(backend.callsTo('/ingest'), 1);
  });
}
