/// The home screen and its tabs — stage 4.
///
/// Nothing here existed before, and neither did a test for the screen it
/// replaced: the old start screen carried the language list, the continue
/// button, the resume prompt, the update notice and sign-out, and not one of
/// them was covered. Replacing it broke no test, which is the wrong kind of
/// quiet.
///
/// Four claims:
///
/// 1. `Root` sends the patient to the right place, and remembers the language.
/// 2. An unusable bundle stops the intake and **only** the intake.
/// 3. The AYUSH card says it is not ready before it is tapped, not after.
/// 4. A tab that cannot load its records shows an empty tab, not an error.
library;

import 'package:flutter/material.dart';
import 'package:medikiosk_app/l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/core/providers.dart';
import 'package:medikiosk_app/core/theme.dart';
import 'package:medikiosk_app/documents/patient_documents.dart';
import 'package:medikiosk_app/home/home_shell.dart';
import 'package:medikiosk_app/home/root.dart';
import 'package:medikiosk_app/identity/history_repository.dart';

import 'bundle_fixture.dart';

Widget wrap(Widget child, List<Override> overrides) => ProviderScope(
      overrides: overrides,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: buildTheme(),
        home: child,
      ),
    );

/// The three things `Root` reads, plus the two tabs that fetch.
///
/// `onboardingSeen` defaults to `true` — "already seen the first-run demo" —
/// so every test written before that demo existed keeps landing straight on
/// the language screen it always expected, and only the tests that are
/// actually about the demo need to say otherwise.
List<Override> edges({
  String? storedLanguage = 'en',
  bool signedIn = true,
  bool onboardingSeen = true,
  List<Visit> visits = const [],
  List<PatientDocument> documents = const [],
}) =>
    [
      storedLanguageProvider.overrideWith((ref) async => storedLanguage),
      signedInProvider.overrideWith((ref) async => signedIn),
      onboardingSeenProvider.overrideWith((ref) async => onboardingSeen),
      visitsProvider.overrideWith((ref) async => visits),
      patientDocumentsProvider.overrideWith((ref) async => documents),
      resumableDraftProvider.overrideWith((ref) async => null),
      signedInPhoneProvider.overrideWith((ref) async => '+919812345678'),
    ];

void main() {
  group('Root sends the patient to the right screen', () {
    testWidgets(
        'a first run welcomes, then demos, then asks for a language',
        (tester) async {
      // Stage 5 put a welcome screen in front of the chooser. It is not a
      // second question: its only control opens the chooser, and the chooser
      // is still the first thing the patient *answers*. A genuine first run
      // — no language stored, and the first-run demo never shown either —
      // now opens the demo screen in between, exactly once.
      await tester.pumpWidget(wrap(
        const Root(),
        edges(storedLanguage: null, onboardingSeen: false),
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('welcome.start')), findsOneWidget);
      expect(find.byKey(const Key('language.hi')), findsNothing);

      await tester.tap(find.byKey(const Key('welcome.start')));
      await tester.pumpAndSettle();
      // The demo, not the chooser, is what a genuine first run sees next.
      expect(find.byKey(const Key('onboarding.getStarted')), findsOneWidget);
      expect(find.byKey(const Key('language.hi')), findsNothing);

      await tester.tap(find.byKey(const Key('onboarding.getStarted')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('language.hi')), findsOneWidget);
    });

    testWidgets(
        'a device that has already seen the demo goes straight to the '
        'language screen',
        (tester) async {
      // No language stored yet — a patient can reach this screen without
      // ever finishing the chooser — but the demo has already played once on
      // this device. It must not play a second time.
      await tester.pumpWidget(wrap(
        const Root(),
        edges(storedLanguage: null, onboardingSeen: true),
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('welcome.start')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('language.hi')), findsOneWidget);
      expect(find.byKey(const Key('onboarding.getStarted')), findsNothing);
    });

    testWidgets('skipping the demo reaches the language screen just the same',
        (tester) async {
      await tester.pumpWidget(wrap(
        const Root(),
        edges(storedLanguage: null, onboardingSeen: false),
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('welcome.start')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('onboarding.skip')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('language.hi')), findsOneWidget);
    });

    testWidgets('a remembered language is not asked for again', (tester) async {
      // The complaint that started stage 4: the chooser reappeared on every
      // launch because the answer lived in memory and died with the process.
      await tester.pumpWidget(wrap(const Root(), edges()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('language.hi')), findsNothing);
      expect(find.byKey(const Key('tab.home')), findsOneWidget);
    });

    testWidgets('English is an answer, not an absence', (tester) async {
      // `languageProvider` defaults to `en`, so "chose English" and "has not
      // chosen" would be the same value if `null` were not the first-run
      // signal — and an English speaker would be asked on every launch.
      await tester.pumpWidget(wrap(const Root(), edges(storedLanguage: 'en')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('tab.home')), findsOneWidget);
    });
  });

  group('the home shell', () {
    testWidgets('offers four destinations and switches between them',
        (tester) async {
      await tester.pumpWidget(wrap(const HomeShell(), edges()));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('home.newIntake')), findsOneWidget);
      expect(find.byKey(const Key('home.ayush')), findsOneWidget);

      await tester.tap(find.byKey(const Key('tab.visits')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('tab.empty')), findsOneWidget);

      await tester.tap(find.byKey(const Key('tab.profile')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('profile.signOut')), findsOneWidget);
    });

    testWidgets('an unusable bundle stops the intake and nothing else',
        (tester) async {
      // §4's refusal used to live on the one screen the app opened with, so a
      // bundle naming a newer contract disabled the only button there was. The
      // patient could not reach their own documents or their own history to
      // look at records that had nothing to do with the version mismatch.
      await tester.pumpWidget(wrap(
        const HomeShell(),
        [
          ...edges(),
          currentBundleProvider.overrideWithValue(
            bundleWith(schemaVersion: '9.9'),
          ),
        ],
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('home.updateRequired')), findsOneWidget);

      await tester.tap(find.byKey(const Key('tab.documents')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('documents.empty')), findsOneWidget);
    });
  });

  group('the AYUSH card', () {
    testWidgets('says it is not ready before it is tapped', (tester) async {
      // A card that looks live and then apologises has already wasted the tap,
      // and this app's rule for a mocked integration (§7.2) is that it says so
      // on screen rather than behaving as though it were real.
      await tester.pumpWidget(wrap(const HomeShell(), edges()));
      await tester.pumpAndSettle();

      final subtitle = AppLocalizations.of(
        tester.element(find.byKey(const Key('home.ayush'))),
      ).notAvailableYet;
      expect(find.text(subtitle), findsOneWidget);

      await tester.tap(find.byKey(const Key('home.ayush')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('ayush.notAvailable')), findsOneWidget);
    });
  });

  group('a tab that cannot load', () {
    testWidgets('is empty, not an error', (tester) async {
      // Both repositories answer a failure with an empty list. A patient whose
      // records could not be fetched must not be told something has gone wrong
      // with their records — nothing has; the phone could not reach the
      // hospital, and the rest of the app still works.
      await tester.pumpWidget(wrap(
        const HomeShell(),
        [
          ...edges(),
          visitsProvider.overrideWith((ref) => Future.error(Exception('offline'))),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('tab.visits')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('tab.empty')), findsOneWidget);
      expect(find.textContaining('Exception'), findsNothing);
    });

    testWidgets('a visit shows what it was about', (tester) async {
      await tester.pumpWidget(wrap(
        const HomeShell(),
        [
          ...edges(visits: [
            Visit(
              intakeId: 'i1',
              receivedAt: DateTime(2026, 9, 4),
              // The patient's own words, which is what the record kept and
              // what the backend now sends instead of only a department code.
              complaint: 'seene mein dard',
              department: 'kayachikitsa',
            ),
          ]),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('tab.visits')));
      await tester.pumpAndSettle();
      expect(find.text('seene mein dard'), findsOneWidget);
      expect(find.text('4 Sep 2026'), findsOneWidget);
    });

    testWidgets('a document shows the page, never the reading', (tester) async {
      // §8. The endpoint behind this tab does not return extracted content and
      // `PatientDocument` has nowhere to put it; this asserts the screen has
      // not grown a way to show one anyway.
      await tester.pumpWidget(wrap(
        const HomeShell(),
        [
          ...edges(documents: [
            PatientDocument(
              documentId: 'd1',
              kind: 'prescription',
              status: 'processed',
              uploadedAt: DateTime(2026, 9, 4),
            ),
          ]),
        ],
      ));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('tab.documents')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('document.d1')), findsOneWidget);
      expect(find.text('Prescription'), findsOneWidget);
      for (final leak in ['Metformin', 'mg', 'confidence', '%']) {
        expect(find.textContaining(leak), findsNothing, reason: leak);
      }
    });
  });
}
