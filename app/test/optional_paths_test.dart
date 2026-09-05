/// The paths a patient may decline — 2/3 §4 versioning, §7.2, §7.3.
///
/// Two properties, and both are about what the app does when something is
/// missing rather than when everything works:
///
/// **ABHA never gates anything.** A patient can skip it, a lookup can find
/// nothing, and the gateway can be down; all three reach the next screen.
///
/// **A bundle this app cannot produce records for stops the intake**, and says
/// so, rather than being half-used.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/content/bundle_repository.dart';
import 'package:medikiosk_app/core/providers.dart';
import 'package:medikiosk_app/identity/abha_repository.dart';
import 'package:medikiosk_app/identity/abha_screen.dart';

import 'fake_api.dart';
import 'screens_test.dart' show wrap;

void main() {
  group('ABHA is never mandatory', () {
    testWidgets('skipping it continues', (tester) async {
      var continued = false;
      await tester.pumpWidget(ProviderScope(
        child: wrap(AbhaScreen(onDone: () => continued = true)),
      ));

      await tester.tap(find.byKey(const Key('abha.skip')));
      await tester.pump();

      expect(continued, isTrue);
    });

    testWidgets('a lookup that finds nothing does not block', (tester) async {
      final backend = FakeBackend()..statuses['/abha'] = 404;
      var continued = false;

      await tester.pumpWidget(ProviderScope(
        overrides: [
          abhaRepositoryProvider
              .overrideWithValue(AbhaRepository(api: fakeApi(backend))),
        ],
        child: wrap(AbhaScreen(onDone: () => continued = true)),
      ));

      await tester.enterText(find.byKey(const Key('abha.address')), 'nobody@sbx');
      await tester.tap(find.byKey(const Key('abha.link')));
      await tester.pumpAndSettle();

      // Told, and still able to carry on. Turning a patient away because a
      // government API was down is not a trade this project makes.
      expect(find.byKey(const Key('abha.notFound')), findsOneWidget);
      expect(continued, isFalse);

      await tester.tap(find.byKey(const Key('abha.skip')));
      await tester.pump();
      expect(continued, isTrue);
    });

    testWidgets('a mocked answer says so on screen', (tester) async {
      // Nobody demos a mocked government integration as a live one.
      final backend = FakeBackend();
      await tester.pumpWidget(ProviderScope(
        overrides: [
          abhaRepositoryProvider
              .overrideWithValue(AbhaRepository(api: fakeApi(backend))),
        ],
        child: wrap(AbhaScreen(onDone: () {})),
      ));

      await tester.enterText(find.byKey(const Key('abha.address')), 'someone@sbx');
      await tester.tap(find.byKey(const Key('abha.link')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('abha.mockNotice')), findsOneWidget);
    });
  });

  group('a bundle this app cannot produce records for', () {
    late Directory cache;
    setUp(() => cache = Directory.systemTemp.createTempSync('medikiosk_bundle'));
    tearDown(() {
      if (cache.existsSync()) cache.deleteSync(recursive: true);
    });

    String bundleJson({required String schemaVersion}) => jsonEncode({
          'bundle_format': '1',
          'content_version': 'v-$schemaVersion',
          'schema_version': schemaVersion,
          'languages': ['en'],
          'sections': ['hpi'],
          'core': <String>[],
          'branches': <String, dynamic>{},
          'ayurveda': <String>[],
          'questions': <dynamic>[],
          'red_flag_rules': <dynamic>[],
        });

    test('is refused rather than half-used', () {
      final bundle = ContentBundle.parse(bundleJson(schemaVersion: '0.9'));
      // §4: no partial compatibility. A record that is half of a newer contract
      // is one the backend will either reject or, worse, accept and misread.
      expect(bundle.isUsable, isFalse);
    });

    test('does not displace a cached bundle that works', () async {
      final backend = FakeBackend();
      final repository =
          BundleRepository(api: fakeApi(backend), cacheDirectory: cache);

      // A working bundle arrives and is cached.
      backend.bodies['/content/bundle'] = bundleJson(schemaVersion: '0.1');
      final first = await repository.load();
      expect(first!.bundle.isUsable, isTrue);

      // The backend rolls forward to a contract this build cannot produce.
      backend.bodies['/content/bundle'] = bundleJson(schemaVersion: '0.9');
      final second = await repository.load();

      // The app keeps working against the version it can still produce, which
      // the backend still accepts. Caching the newer one would brick an app
      // that was holding a perfectly usable copy of the older.
      expect(second!.bundle.schemaVersion, '0.1');
      expect(second.fromCache, isTrue);
    });

    test('is handed back when there is no cache to fall back on', () async {
      final backend = FakeBackend()
        ..bodies['/content/bundle'] = bundleJson(schemaVersion: '0.9');
      final repository =
          BundleRepository(api: fakeApi(backend), cacheDirectory: cache);

      final result = await repository.load();

      // Nothing to run, so the UI needs something to refuse on — that is what
      // puts `updateRequired` on the start screen.
      expect(result!.bundle.isUsable, isFalse);
    });
  });
}
