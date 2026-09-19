/// The two screens whose behaviour is a safety property — 2/3 §5, §6.
library;

import 'package:flutter/material.dart';
import 'package:medikiosk_app/l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/core/theme.dart';
import 'package:medikiosk_app/intake/screens/question_screen.dart';
import 'package:medikiosk_app/intake/widgets/interview_ui.dart';
import 'package:medikiosk_app/intake/screens/urgent_care_screen.dart';

Widget wrap(Widget child, {Locale locale = const Locale('en'), double scale = 1}) =>
    ProviderScope(
      child: _app(child, locale: locale, scale: scale),
    );

Widget _app(Widget child, {required Locale locale, required double scale}) =>
    MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildTheme(),
      builder: (context, widget) => MediaQuery(
        data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)),
        child: widget!,
      ),
      home: child,
    );

Question sample({bool allowSkip = true, Map<String, String>? prompts}) => Question(
      questionId: 'q',
      fieldId: 'severity',
      section: 'hpi',
      answerType: AnswerType.yesNoUnknown,
      prompts: prompts ?? const {'en': 'Are you short of breath?', 'hi': 'क्या साँस फूलती है?'},
      allowSkip: allowSkip,
    );

QuestionScreen screen({
  bool allowSkip = true,
  String language = 'en',
  VoidCallback? onBack,
  Map<String, String>? prompts,
  double? progress,
}) =>
    QuestionScreen(
      question: sample(allowSkip: allowSkip, prompts: prompts),
      language: language,
      onAnswered: (_, __) {},
      onDontKnow: () {},
      onSkip: () {},
      sectionsDone: 3,
      sectionsTotal: 7,
      progress: progress,
      onBack: onBack,
    );

void main() {
  group('the question screen', () {
    testWidgets('shows the prompt in the chosen language', (tester) async {
      await tester.pumpWidget(wrap(screen(language: 'hi'), locale: const Locale('hi')));
      expect(find.text('क्या साँस फूलती है?'), findsOneWidget);
      expect(find.text('Are you short of breath?'), findsNothing);
    });

    testWidgets('the number the patient reads is sections, not a percentage',
        (tester) async {
      // The bar moves per question so it does not look frozen, but the number
      // under it stays a count. A percentage would imply a precision the
      // branching does not have, and it is the number a patient quotes back.
      await tester.pumpWidget(wrap(screen(progress: 0.42)));
      expect(find.text('Section 3 of 7'), findsOneWidget);
      expect(find.textContaining('%'), findsNothing);
    });

    testWidgets('back is offered when there is somewhere to go back to',
        (tester) async {
      await tester.pumpWidget(wrap(screen(onBack: () {})));
      expect(find.byKey(const Key('question.back')), findsOneWidget);
    });

    testWidgets('back is absent on the first question', (tester) async {
      await tester.pumpWidget(wrap(screen()));
      expect(find.byKey(const Key('question.back')), findsNothing);
    });

    testWidgets('an unskippable question offers no skip', (tester) async {
      await tester.pumpWidget(wrap(screen(allowSkip: false)));
      expect(find.byKey(const Key('answer.dont_know')), findsOneWidget);
      expect(find.byKey(const Key('answer.skip')), findsNothing);
    });

    testWidgets('at 200% text scale nothing overflows', (tester) async {
      // §15 item 14. The affordance that must not be pushed off screen is
      // "I don't know" — its disappearance is a clinical problem, because the
      // patient's only remaining options are to guess or to skip.
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(wrap(screen(), scale: 2));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      final dontKnow = find.byKey(const Key('answer.dont_know'));
      expect(dontKnow, findsOneWidget);
      await tester.scrollUntilVisible(dontKnow, 200);
      expect(tester.getSize(dontKnow).height,
          greaterThanOrEqualTo(Sizes.minTouchTarget));
    });

    testWidgets('a missing prompt renders the field id, never English',
        (tester) async {
      // Unreachable via the walker, which never offers such a question. Asserted
      // so that if the invariant breaks the failure is visible rather than a
      // patient silently answering an English question they did not choose.
      await tester.pumpWidget(wrap(
        screen(language: 'ta', prompts: const {'en': 'Only English'}),
        locale: const Locale('ta'),
      ));
      expect(find.text('Only English'), findsNothing);
      expect(find.text('severity'), findsOneWidget);
    });
  });

  group('the more-below hint', () {
    // The hero mic (§16 — voice on every question now) is the single biggest
    // thing on this screen, and on a short viewport that leaves the option
    // tiles right at the bottom edge with nothing visibly cueing that more of
    // the question exists. This is the affordance that fixes it.
    testWidgets('shows while content is cut off, hides once scrolled to the end',
        (tester) async {
      // Short enough that a yes/no question — mic, two options, don't-know,
      // skip — does not fit without scrolling.
      tester.view.physicalSize = const Size(400, 500);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(wrap(screen()));
      await tester.pumpAndSettle();

      double opacity() => tester
          .widget<AnimatedOpacity>(find.descendant(
            of: find.byType(MoreBelowFade),
            matching: find.byType(AnimatedOpacity),
          ))
          .opacity;

      expect(opacity(), 1,
          reason: 'the options do not fit a 500px-tall screen');

      await tester.drag(find.byType(SingleChildScrollView), const Offset(0, -2000));
      await tester.pumpAndSettle();

      expect(opacity(), 0,
          reason: 'nothing left below once scrolled all the way down');
    });

    testWidgets('never blocks a tap on what is underneath it', (tester) async {
      tester.view.physicalSize = const Size(400, 500);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      String? recorded;
      await tester.pumpWidget(wrap(QuestionScreen(
        question: sample(),
        language: 'en',
        onAnswered: (_, text) => recorded = text,
        onDontKnow: () {},
        onSkip: () {},
        sectionsDone: 3,
        sectionsTotal: 7,
      )));
      await tester.pumpAndSettle();

      // Scroll the "no" option into the same screen region the fade sits
      // over, then tap it there — decoration must never win a hit test
      // against the option it is drawn on top of.
      await tester.drag(find.byType(SingleChildScrollView), const Offset(0, -300));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('option.no')));
      await tester.pumpAndSettle();

      expect(recorded, isNotNull);
    });
  });

  group('the urgent-care screen', () {
    Widget urgent({VoidCallback? nearest, VoidCallback? ack}) => wrap(
          UrgentCareScreen(
            emergencyNumber: '108',
            onShowNearestHospital: nearest ?? () {},
            onAcknowledge: ack ?? () {},
          ),
        );

    testWidgets('it says what to do and names no condition', (tester) async {
      await tester.pumpWidget(urgent());
      expect(find.byKey(const Key('urgent.title')), findsOneWidget);
      expect(find.textContaining('108'), findsOneWidget);

      for (final word in ['heart', 'attack', 'stroke', 'infarction', 'may be']) {
        expect(find.textContaining(word, findRichText: true), findsNothing,
            reason: 'the screen must never suggest what is wrong');
      }
    });

    testWidgets('there is no way to continue the intake', (tester) async {
      // §6.4. Not disabled, not behind a confirmation — absent.
      await tester.pumpWidget(urgent());
      expect(find.byKey(const Key('urgent.nearest')), findsOneWidget);
      expect(find.byKey(const Key('urgent.acknowledge')), findsOneWidget);

      for (final label in ['Continue', 'Skip', 'Back', 'Next']) {
        expect(find.text(label), findsNothing);
      }
      expect(find.byType(BackButton), findsNothing);
    });

    testWidgets('the system back gesture cannot dismiss it', (tester) async {
      await tester.pumpWidget(urgent());
      final scope = tester.widget<PopScope>(find.byType(PopScope));
      expect(scope.canPop, isFalse);
    });

    testWidgets('the emergency number is a parameter, not a constant',
        (tester) async {
      // 108 is not universal across Indian states, so a hospital must be able
      // to change it without an app release.
      await tester.pumpWidget(wrap(UrgentCareScreen(
        emergencyNumber: '102',
        onShowNearestHospital: () {},
        onAcknowledge: () {},
      )));
      expect(find.textContaining('102'), findsOneWidget);
    });
  });
}
