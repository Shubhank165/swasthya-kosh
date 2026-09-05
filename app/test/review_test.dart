/// The review screen — 2/3 §5 screen 10, §8.
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/content/answer.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/core/theme.dart';
import 'package:medikiosk_app/intake/screens/review_screen.dart';
import 'package:medikiosk_app/intake/screens/submitted_screen.dart';

ContentBundle bundle() => ContentBundle.parse(jsonEncode({
      'bundle_format': '1',
      'content_version': 'test',
      'schema_version': '0.1',
      'languages': ['en', 'hi'],
      'sections': ['chief_complaint', 'medications', 'allergies'],
      'core': <String>[],
      'branches': <String, dynamic>{},
      'ayurveda': <String>[],
      'questions': [
        {
          'question_id': 'q.cc',
          'field_id': 'chief_complaint',
          'section': 'chief_complaint',
          'answer_type': 'single_choice',
          'prompts': {'en': 'What brings you in?', 'hi': 'आप क्यों आए हैं?'},
          'options': ['fever'],
          'required': true,
          'allow_skip': false,
          'allow_unknown': true,
        },
        {
          'question_id': 'q.meds',
          'field_id': 'current_medications',
          'section': 'medications',
          'answer_type': 'free_text',
          'prompts': {'en': 'Which medicines?', 'hi': 'कौन सी दवाएँ?'},
          'required': true,
          'allow_skip': true,
          'allow_unknown': true,
        },
      ],
      'red_flag_rules': <dynamic>[],
    }));

Map<String, Answer> answers() => {
      'q.cc': const Answer(
        questionId: 'q.cc',
        fieldId: 'chief_complaint',
        status: FieldStatus.answered,
        value: CodedValue('fever'),
        originalText: 'Fever',
        language: 'en',
      ),
      'q.meds': const Answer(
        questionId: 'q.meds',
        fieldId: 'current_medications',
        status: FieldStatus.answered,
        value: TextValue('Metformin 500'),
        originalText: 'Metformin 500',
        language: 'en',
      ),
      'q.skipped': const Answer(
        questionId: 'q.skipped',
        fieldId: 'tobacco',
        status: FieldStatus.notAsked,
        language: 'en',
      ),
    };

Widget wrap(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildTheme(),
      home: child,
    );

void main() {
  group('review', () {
    testWidgets('shows the patient their own words', (tester) async {
      // Not the normalised code. A patient checking their answer needs to
      // recognise it.
      await tester.pumpWidget(wrap(ReviewScreen(
        bundle: bundle(),
        answers: answers(),
        language: 'en',
        onEdit: (_) {},
        onSubmit: () {},
      )));
      expect(find.text('Metformin 500'), findsOneWidget);
      expect(find.text('fever'), findsNothing, reason: 'the code, not the label');
      expect(find.text('Fever'), findsOneWidget);
    });

    testWidgets('medicines and allergies come first', (tester) async {
      // §5 names them explicitly: they are what a physician acts on soonest and
      // what a patient is most likely to have mistyped.
      await tester.pumpWidget(wrap(ReviewScreen(
        bundle: bundle(),
        answers: answers(),
        language: 'en',
        onEdit: (_) {},
        onSubmit: () {},
      )));
      final meds = tester.getTopLeft(find.byKey(const Key('review.q.meds')));
      final cc = tester.getTopLeft(find.byKey(const Key('review.q.cc')));
      expect(meds.dy, lessThan(cc.dy));
    });

    testWidgets('unsettled answers are not listed', (tester) async {
      // A wall of "not asked" rows would bury the answers that need checking.
      await tester.pumpWidget(wrap(ReviewScreen(
        bundle: bundle(),
        answers: answers(),
        language: 'en',
        onEdit: (_) {},
        onSubmit: () {},
      )));
      expect(find.byKey(const Key('review.q.skipped')), findsNothing);
    });

    testWidgets('every answer can be corrected before submitting', (tester) async {
      String? edited;
      await tester.pumpWidget(wrap(ReviewScreen(
        bundle: bundle(),
        answers: answers(),
        language: 'en',
        onEdit: (id) => edited = id,
        onSubmit: () {},
      )));
      await tester.tap(find.descendant(
        of: find.byKey(const Key('review.q.meds')),
        matching: find.byType(TextButton),
      ));
      expect(edited, 'q.meds');
    });

    testWidgets('it renders in the patient language', (tester) async {
      await tester.pumpWidget(wrap(ReviewScreen(
        bundle: bundle(),
        answers: answers(),
        language: 'hi',
        onEdit: (_) {},
        onSubmit: () {},
      )));
      expect(find.text('कौन सी दवाएँ?'), findsOneWidget);
    });
  });

  group('submitted', () {
    testWidgets('an accepted intake shows the code and where to use it',
        (tester) async {
      await tester.pumpWidget(wrap(const SubmittedScreen(
        referenceCode: 'MK-4821',
        hospitalName: 'AIIA, New Delhi',
        queued: false,
      )));
      expect(find.text('MK-4821'), findsOneWidget);
      expect(find.text('Show this code at the registration desk.'), findsOneWidget);
    });

    testWidgets('a queued intake says so rather than implying acceptance',
        (tester) async {
      // A code the patient believes is registered when it is not is worse than
      // a short wait.
      await tester.pumpWidget(wrap(const SubmittedScreen(
        referenceCode: 'MK-4821',
        hospitalName: 'AIIA, New Delhi',
        queued: true,
      )));
      expect(
        find.text('Saved on this phone. It will be sent when you are back online.'),
        findsOneWidget,
      );
    });

    testWidgets('no appointment is offered or implied', (tester) async {
      // §7.4: the app does not book. It is not in the problem statement and it
      // is scope this build does not need.
      await tester.pumpWidget(wrap(const SubmittedScreen(
        referenceCode: 'MK-4821',
        hospitalName: 'AIIA',
        queued: false,
      )));
      for (final word in ['appointment', 'booked', 'slot', 'token number']) {
        expect(find.textContaining(word), findsNothing);
      }
    });
  });
}
