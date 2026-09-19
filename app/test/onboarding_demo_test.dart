/// The first-run demo — Skip, Replay, and Get started all have to work, and
/// none of them may be able to strand a patient on this screen forever.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/core/theme.dart';
import 'package:medikiosk_app/home/onboarding_demo_screen.dart';
import 'package:medikiosk_app/l10n/app_localizations.dart';

Widget wrap(Widget child) => ProviderScope(
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: buildTheme(),
        home: child,
      ),
    );

void main() {
  group('the first-run demo', () {
    testWidgets('opens on the welcome frame, with all four controls present',
        (tester) async {
      await tester.pumpWidget(wrap(const OnboardingDemoScreen()));
      await tester.pump();

      expect(find.text('Welcome to MediKiosk'), findsOneWidget);
      expect(find.byKey(const Key('onboarding.skip')), findsOneWidget);
      expect(find.byKey(const Key('onboarding.replay')), findsOneWidget);
      expect(find.byKey(const Key('onboarding.getStarted')), findsOneWidget);

      // Drains the autoplay timer to completion rather than leaving the test
      // with one still pending — the assertions above already happened, this
      // is purely so the test finishes clean.
      await tester.pumpAndSettle();
    });

    testWidgets('autoplays forward, and replay takes it back to the start',
        (tester) async {
      await tester.pumpWidget(wrap(const OnboardingDemoScreen()));
      await tester.pump();
      expect(find.text('Welcome to MediKiosk'), findsOneWidget);

      // Past the first couple of frames on its own — nobody has touched
      // anything.
      await tester.pumpAndSettle();
      expect(find.text('Welcome to MediKiosk'), findsNothing);

      await tester.tap(find.byKey(const Key('onboarding.replay')));
      await tester.pumpAndSettle();
      expect(find.text('Welcome to MediKiosk'), findsOneWidget);
    });

    testWidgets('skip reaches the real language screen', (tester) async {
      await tester.pumpWidget(wrap(const OnboardingDemoScreen()));
      await tester.pump();

      await tester.tap(find.byKey(const Key('onboarding.skip')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('language.hi')), findsOneWidget);
      expect(find.byKey(const Key('onboarding.skip')), findsNothing);
    });

    testWidgets('get started reaches the real language screen too',
        (tester) async {
      await tester.pumpWidget(wrap(const OnboardingDemoScreen()));
      await tester.pump();

      await tester.tap(find.byKey(const Key('onboarding.getStarted')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('language.hi')), findsOneWidget);
    });

    testWidgets('the autoplay stops on its own once every frame has shown',
        (tester) async {
      // If the auto-advance never stopped, this pumpAndSettle would not
      // return — see the note on `_DemoMic`'s bounded pulse for the other
      // half of that same guarantee.
      await tester.pumpWidget(wrap(const OnboardingDemoScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('onboarding.getStarted')), findsOneWidget);
    });
  });
}
