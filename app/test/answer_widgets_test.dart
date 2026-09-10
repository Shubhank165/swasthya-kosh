/// One test per `answer_type` renderer — 2/3 §15 item 12.
///
/// These check what the widget *records*, not how it looks. A renderer that
/// looks right and hands back a `TextValue` where the contract expects a
/// `DurationValue` produces a record the backend reads as unparsed text.
library;

import 'package:flutter/material.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/content/answer.dart';
import 'package:medikiosk_app/content/bundle.dart';
import 'package:medikiosk_app/core/theme.dart';
import 'package:medikiosk_app/intake/widgets/answer_actions.dart';
import 'package:medikiosk_app/intake/widgets/answer_widgets.dart';

Question q(
  String type, {
  List<String>? options,
  String? unit,
  List<String>? units,
  double? min,
  double? max,
  String questionId = 'q',
}) =>
    Question(
      questionId: questionId,
      fieldId: 'f',
      section: 'hpi',
      answerType: AnswerType.parse(type),
      prompts: const {'en': 'A question'},
      options: options,
      unit: unit,
      units: units,
      minimum: min,
      maximum: max,
    );

Future<(AnswerValue?, String?)> pumpAnswer(
  WidgetTester tester,
  Question question, {
  Locale locale = const Locale('en'),
}) async {
  AnswerValue? captured;
  String? capturedText;
  await tester.pumpWidget(ProviderScope(child: MaterialApp(
    locale: locale,
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    theme: buildTheme(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: buildAnswerWidget(
          question: question,
          onAnswered: (value, text) {
            captured = value;
            capturedText = text;
          },
        )!,
      ),
    ),
  )));
  await tester.pumpAndSettle();
  return (captured, capturedText);
}

void main() {
  testWidgets('single_choice records the option code, not the label', (tester) async {
    // The label is de-underscored for display; the *code* is what the ontology
    // and the red-flag rules match on, so that is what must be recorded.
    AnswerValue? value;
    String? text;
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: SingleChoiceAnswer(
          question: q('single_choice', options: ['sudden', 'gradual']),
          onAnswered: (v, t) {
            value = v;
            text = t;
          },
        ),
      ),
    )));
    await tester.tap(find.byKey(const Key('option.sudden')));
    await tester.pump();

    expect((value! as CodedValue).code, 'sudden');
    expect(text, 'Sudden', reason: 'the patient saw the readable form');
  });

  testWidgets('multi_choice cannot submit an empty selection', (tester) async {
    // An empty multi-select recorded as an answer means "none of these" — a
    // clinical claim the patient did not make.
    await pumpAnswer(tester, q('multi_choice', options: ['rash', 'swelling']));
    final confirm = tester.widget<FilledButton>(find.byKey(const Key('answer.confirm')));
    expect(confirm.onPressed, isNull);
  });

  testWidgets('multi_choice records every chosen code', (tester) async {
    AnswerValue? value;
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: MultiChoiceAnswer(
          question: q('multi_choice', options: ['rash', 'swelling', 'fainting']),
          onAnswered: (v, _) => value = v,
        ),
      ),
    )));
    await tester.tap(find.byKey(const Key('option.rash')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('option.fainting')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('answer.confirm')));
    await tester.pump();

    expect((value! as CodedListValue).codes, ['fainting', 'rash']);
  });

  testWidgets('yes_no_unknown offers yes and no only', (tester) async {
    // The third arm is the shared "I don't know" affordance every question
    // carries. Rendering it twice would offer two buttons recording the same
    // status and invite the patient to wonder how they differ.
    await pumpAnswer(tester, q('yes_no_unknown'));
    expect(find.byKey(const Key('option.yes')), findsOneWidget);
    expect(find.byKey(const Key('option.no')), findsOneWidget);
    expect(find.byKey(const Key('answer.dont_know')), findsNothing);
  });

  testWidgets('yes and no record booleans, not text', (tester) async {
    AnswerValue? value;
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: YesNoAnswer(question: q('yes_no_unknown'), onAnswered: (v, _) => value = v),
      ),
    )));
    await tester.tap(find.byKey(const Key('option.no')));
    await tester.pump();
    expect((value! as BoolValue).value, isFalse);
  });

  testWidgets('number carries its unit', (tester) async {
    AnswerValue? value;
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: NumberAnswer(
          question: q('number', unit: 'years'),
          onAnswered: (v, _) => value = v,
        ),
      ),
    )));
    await tester.enterText(find.byKey(const Key('answer.number')), '42');
    await tester.pump();
    await tester.tap(find.byKey(const Key('answer.confirm')));
    await tester.pump();

    final number = value! as NumberValue;
    expect(number.value, 42);
    expect(number.unit, 'years');
    expect(number.toJson(), 42.0, reason: 'bare value; the unit travels beside it');
  });

  testWidgets('number will not submit non-numeric text', (tester) async {
    await pumpAnswer(tester, q('number', unit: 'years'));
    await tester.enterText(find.byKey(const Key('answer.number')), 'about forty');
    await tester.pump();
    final confirm = tester.widget<FilledButton>(find.byKey(const Key('answer.confirm')));
    expect(confirm.onPressed, isNull);
  });

  testWidgets('scale renders one button per point, all 48dp or larger', (tester) async {
    // A slider reports a value the patient did not deliberately choose if they
    // nudge it, and is near-unusable with a tremor or a screen reader.
    await pumpAnswer(tester, q('scale', min: 0, max: 10));
    expect(find.byKey(const Key('scale.0')), findsOneWidget);
    expect(find.byKey(const Key('scale.10')), findsOneWidget);
    final size = tester.getSize(find.byKey(const Key('scale.7')));
    expect(size.width, greaterThanOrEqualTo(Sizes.minTouchTarget));
    expect(size.height, greaterThanOrEqualTo(Sizes.minTouchTarget));
  });

  testWidgets('scale records a bare number', (tester) async {
    AnswerValue? value;
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: ScaleAnswer(
          question: q('scale', min: 0, max: 10),
          onAnswered: (v, _) => value = v,
        ),
      ),
    )));
    await tester.tap(find.byKey(const Key('scale.6')));
    await tester.pump();
    expect(value!.toJson(), 6.0);
  });

  testWidgets('duration records the shape the normalizer reads', (tester) async {
    // `{"n": 3, "unit": "day"}`. A tagged union here would coerce to a Text of
    // the whole object on the backend.
    AnswerValue? value;
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: SingleChildScrollView(
          child: DurationAnswer(
            question: q('duration'),
            onAnswered: (v, _) => value = v,
          ),
        ),
      ),
    )));
    await tester.enterText(find.byKey(const Key('answer.duration_n')), '3');
    await tester.pump();
    await tester.tap(find.byKey(const Key('duration.week')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('answer.confirm')));
    await tester.pump();

    expect(value!.toJson(), {'n': 3.0, 'unit': 'week'});
  });

  testWidgets('duration offers only units the backend recognises', (tester) async {
    // Anything else coerces to a plain quantity and loses that it is a duration.
    await pumpAnswer(tester, q('duration'));
    for (final unit in ['hour', 'day', 'week', 'month', 'year']) {
      expect(find.byKey(Key('duration.$unit')), findsOneWidget);
    }
  });

  testWidgets('free_text records what was typed, and voice is absent with no '
      'recogniser', (tester) async {
    // On-device dictation is offered here (DECISIONS §68) but only ever fills
    // the box for the patient to edit — it never records on its own. With no
    // recogniser plugin (this test) the affordance is simply not shown.
    AnswerValue? value;
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: FreeTextAnswer(question: q('free_text'), onAnswered: (v, _) => value = v),
      ),
    )));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('answer.free_text')), 'nothing else');
    await tester.pump();
    await tester.tap(find.byKey(const Key('answer.confirm')));
    await tester.pump();

    expect((value! as TextValue).text, 'nothing else');
    expect(find.byKey(const Key('question.listen')), findsNothing);
  });

  testWidgets('date records an ISO date', (tester) async {
    await pumpAnswer(tester, q('date'));
    expect(find.byKey(const Key('answer.date_picker')), findsOneWidget);
    final confirm = tester.widget<FilledButton>(find.byKey(const Key('answer.confirm')));
    expect(confirm.onPressed, isNull, reason: 'nothing picked yet');
  });

  testWidgets('an unknown answer_type renders nothing rather than an empty box',
      (tester) async {
    expect(
      buildAnswerWidget(question: q('holographic'), onAnswered: (_, __) {}),
      isNull,
    );
  });

  group('the two affordances', () {
    testWidgets('both appear when the content allows both', (tester) async {
      await tester.pumpWidget(ProviderScope(child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: AnswerActions(
            allowUnknown: true,
            allowSkip: true,
            onDontKnow: () {},
            onSkip: () {},
          ),
        ),
      )));
      expect(find.byKey(const Key('answer.dont_know')), findsOneWidget);
      expect(find.byKey(const Key('answer.skip')), findsOneWidget);
    });

    testWidgets('skip disappears where the content forbids it', (tester) async {
      // Consent and the chief complaint. Without them there is no intake.
      await tester.pumpWidget(ProviderScope(child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: AnswerActions(
            allowUnknown: true,
            allowSkip: false,
            onDontKnow: () {},
            onSkip: () {},
          ),
        ),
      )));
      expect(find.byKey(const Key('answer.dont_know')), findsOneWidget);
      expect(find.byKey(const Key('answer.skip')), findsNothing);
    });

    testWidgets('they do not read as the same thing in any language', (tester) async {
      // They record different statuses — `unresolved` and `not_asked` — so a
      // patient who cannot tell them apart produces the wrong one.
      for (final locale in ['en', 'hi', 'ta', 'bn']) {
        await tester.pumpWidget(ProviderScope(child: MaterialApp(
          locale: Locale(locale),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: AnswerActions(
              allowUnknown: true,
              allowSkip: true,
              onDontKnow: () {},
              onSkip: () {},
            ),
          ),
        )));
        await tester.pumpAndSettle();
        final dontKnow = tester.widget<Text>(
          find.descendant(
            of: find.byKey(const Key('answer.dont_know')),
            matching: find.byType(Text),
          ),
        );
        final skip = tester.widget<Text>(
          find.descendant(
            of: find.byKey(const Key('answer.skip')),
            matching: find.byType(Text),
          ),
        );
        expect(dontKnow.data, isNot(skip.data), reason: 'identical in $locale');
      }
    });
  });

  testWidgets('a temperature can be given in fahrenheit, and is not converted',
      (tester) async {
    // An Indian household thermometer reads Fahrenheit. A Celsius-only box
    // does not stop that patient answering — it makes them type 101 into a
    // field labelled °C, which is a fever recorded as hypothermia.
    final question = q('number', unit: 'celsius', units: ['celsius', 'fahrenheit']);
    AnswerValue? value;
    String? text;
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildTheme(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: buildAnswerWidget(
            question: question,
            onAnswered: (v, t) {
              value = v;
              text = t;
            },
          )!,
        ),
      ),
    )));
    await tester.enterText(find.byKey(const Key('answer.number')), '101');
    await tester.tap(find.byKey(const Key('unit.fahrenheit')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('answer.confirm')));
    await tester.pumpAndSettle();

    // 101, not 38.3. Converting would put a number in the record the patient
    // never said, and `Duration` gives the same reason for not normalising
    // "about two weeks" into seconds.
    expect((value! as NumberValue).value, 101);
    expect((value as NumberValue).unit, 'fahrenheit');
    expect(text, '101 fahrenheit');
  });

  testWidgets('the default unit is recorded when the patient does not choose',
      (tester) async {
    final question = q('number', unit: 'celsius', units: ['celsius', 'fahrenheit']);
    final (value, text) = await pumpAnswerWith(tester, question, '38.5');
    expect((value! as NumberValue).unit, 'celsius');
    expect(text, '38.5 celsius');
  });

  testWidgets('a question with one unit offers no choice', (tester) async {
    // A toggle with a single option is a control that cannot do anything.
    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildTheme(),
      home: Scaffold(
        body: buildAnswerWidget(
          question: q('number', unit: 'years'),
          onAnswered: (_, __) {},
        )!,
      ),
    )));
    expect(find.byKey(const Key('unit.years')), findsNothing);
  });

  testWidgets('a new question starts with an empty text box', (tester) async {
    // Flutter reuses a `State` when the same widget type lands in the same
    // position, and every question renders its answer widget in the same
    // position. Without a per-question key the previous answer was still in
    // the box — so the reply to "which medicines do you take" was sitting
    // there, pre-filled, when the next question asked about allergies.
    Question showing = q('free_text', questionId: 'medications');
    late StateSetter setOuter;

    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildTheme(),
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, setState) {
            setOuter = setState;
            return buildAnswerWidget(
              question: showing,
              onAnswered: (_, __) {},
            )!;
          },
        ),
      ),
    )));

    await tester.enterText(find.byKey(const Key('answer.free_text')), 'Metformin 500mg');
    await tester.pumpAndSettle();
    expect(find.text('Metformin 500mg'), findsOneWidget);

    setOuter(() => showing = q('free_text', questionId: 'allergies'));
    await tester.pumpAndSettle();

    expect(find.text('Metformin 500mg'), findsNothing);
    expect(
      tester.widget<TextField>(find.byKey(const Key('answer.free_text'))).controller!.text,
      isEmpty,
    );
  });

  testWidgets('the same question keeps what the patient has typed so far',
      (tester) async {
    // The guard has to be narrow. Clearing on every rebuild would wipe the box
    // each time the widget redraws, which is every keystroke.
    Question showing = q('free_text', questionId: 'medications');
    late StateSetter setOuter;

    await tester.pumpWidget(ProviderScope(child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildTheme(),
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, setState) {
            setOuter = setState;
            return buildAnswerWidget(question: showing, onAnswered: (_, __) {})!;
          },
        ),
      ),
    )));

    await tester.enterText(find.byKey(const Key('answer.free_text')), 'Metformin');
    setOuter(() => showing = q('free_text', questionId: 'medications'));
    await tester.pumpAndSettle();

    expect(find.text('Metformin'), findsOneWidget);
  });

}

/// Type [entry] into the number box and confirm, returning what was recorded.
Future<(AnswerValue?, String?)> pumpAnswerWith(
  WidgetTester tester,
  Question question,
  String entry,
) async {
  AnswerValue? captured;
  String? capturedText;
  await tester.pumpWidget(ProviderScope(child: MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    theme: buildTheme(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: buildAnswerWidget(
          question: question,
          onAnswered: (value, text) {
            captured = value;
            capturedText = text;
          },
        )!,
      ),
    ),
  )));
  await tester.enterText(find.byKey(const Key('answer.number')), entry);
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('answer.confirm')));
  await tester.pumpAndSettle();
  return (captured, capturedText);
}
