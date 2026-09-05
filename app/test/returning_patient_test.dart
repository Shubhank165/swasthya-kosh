/// The returning-patient check — 2/3 §5 screen 5.
library;

import 'package:flutter/material.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/core/theme.dart';
import 'package:medikiosk_app/intake/screens/returning_patient_screen.dart';

const items = [
  CarriedItem(
    fieldId: 'past_medical',
    label: 'Diabetes',
    recordedOn: 'Recorded 12 June 2026',
  ),
  CarriedItem(
    fieldId: 'current_medications',
    label: 'Metformin 500',
    recordedOn: 'Recorded 12 June 2026',
  ),
];

Widget wrap(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      theme: buildTheme(),
      home: child,
    );

void main() {
  testWidgets('it shows what the hospital already holds, in the patient words',
      (tester) async {
    await tester.pumpWidget(
        wrap(ReturningPatientScreen(items: items, onDone: (_) {})));
    expect(find.text('Diabetes'), findsOneWidget);
    expect(find.text('Metformin 500'), findsOneWidget);
    expect(find.text('Recorded 12 June 2026'), findsNWidgets(2));
  });

  testWidgets('"not sure" is a third answer, distinct from no', (tester) async {
    // A patient unsure whether they still take a medicine has not said they
    // stopped. Recording it as a stop would remove a drug from their history on
    // a guess.
    await tester.pumpWidget(
        wrap(ReturningPatientScreen(items: items, onDone: (_) {})));
    expect(find.byKey(const Key('carry.past_medical.stillCorrect')), findsOneWidget);
    expect(find.byKey(const Key('carry.past_medical.noLongerCorrect')), findsOneWidget);
    expect(find.byKey(const Key('carry.past_medical.notSure')), findsOneWidget);
  });

  testWidgets('nothing proceeds until every item is decided', (tester) async {
    // An undecided item silently becoming "still correct" is the system
    // asserting a clinical fact on the patient's behalf.
    await tester.pumpWidget(
        wrap(ReturningPatientScreen(items: items, onDone: (_) {})));

    final button = find.byKey(const Key('carry.continue'));
    expect(tester.widget<FilledButton>(button).onPressed, isNull);

    await tester.tap(find.byKey(const Key('carry.past_medical.stillCorrect')));
    await tester.pump();
    expect(tester.widget<FilledButton>(button).onPressed, isNull,
        reason: 'one of two decided');

    await tester.tap(
        find.byKey(const Key('carry.current_medications.noLongerCorrect')));
    await tester.pump();
    expect(tester.widget<FilledButton>(button).onPressed, isNotNull);
  });

  testWidgets('the decisions reach the caller', (tester) async {
    Map<String, CarryDecision>? captured;
    await tester.pumpWidget(
        wrap(ReturningPatientScreen(items: items, onDone: (d) => captured = d)));

    await tester.tap(find.byKey(const Key('carry.past_medical.stillCorrect')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('carry.current_medications.notSure')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('carry.continue')));
    await tester.pump();

    expect(captured, {
      'past_medical': CarryDecision.stillCorrect,
      'current_medications': CarryDecision.notSure,
    });
  });
}
