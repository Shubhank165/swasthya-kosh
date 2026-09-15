import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_flutter/models/models.dart';
import 'package:medikiosk_flutter/screens/interview_screen.dart';
import 'package:medikiosk_flutter/screens/report_screen.dart';

void main() {
  testWidgets('bleeding question has a typed answer fallback', (tester) async {
    final answers = <String>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(
      child: InterviewScreen(questionText: 'Any bleeding?', questionId: 'ask_bleeding',
        onSubmitAnswer: answers.add),
    ))));
    await tester.enterText(find.byType(TextField), 'no');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    expect(answers, ['no']);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('age band does not invent exact age', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(
      child: InterviewScreen(questionText: 'Age?', questionId: 'ask_age',
        onSubmitAnswer: (_) {}),
    ))));
    expect(find.byType(TextField), findsOneWidget);
    expect(find.textContaining('(Adult)'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('intake report slip displays patient and summary', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ReportScreen(
          profile: PatientProfile(name: 'Ramesh Kumar', age: 42, gender: 'MALE'),
          clinicalAnswers: [
            ClinicalAnswerRecord(
              questionText: 'Chief Complaint',
              answerText: 'Fever and cold',
              timestamp: DateTime.now(),
            )
          ],
          extractedDocumentLines: const ['Paracetamol 500mg'],
          onNewPatient: () {},
        ),
      ),
    ));
    expect(find.text('Ramesh Kumar'), findsOneWidget);
    expect(find.text('Fever and cold'), findsOneWidget);
  });

  /// The slip is laid out for the kiosk tablet (SM-T505: 2000x1200 at 1.5x = 1333x800 logical).
  /// The 800x600 default test surface is narrower than any device this runs on, so a layout
  /// asserted at that size proves nothing about the screen a patient sees.
  Future<void> pumpOnTablet(WidgetTester tester, Widget widget) async {
    tester.view.physicalSize = const Size(2000, 1200);
    tester.view.devicePixelRatio = 1.5;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(widget);
  }

  Widget slipWith(Map<String, dynamic>? report) => MaterialApp(
        home: Scaffold(
          body: ReportScreen(
            reportData: report,
            profile: PatientProfile(name: 'Ramesh Kumar', age: 42, gender: 'MALE'),
            clinicalAnswers: const [],
            extractedDocumentLines: const [],
            onNewPatient: () {},
          ),
        ),
      );

  testWidgets('slip prints the Prakriti the server scored', (tester) async {
    await pumpOnTablet(tester, slipWith({
      'prakriti': {
        'prakriti': 'Kaphaja',
        'prakriti_hi': 'कफज',
        'marks': {'vata': 3, 'pitta': 4, 'kapha': 14},
        'scoring_reviewed': false,
        'recorded_at': '2026-09-07T01:00:00Z',
      },
    }));
    expect(find.textContaining('Kaphaja'), findsOneWidget);
    expect(find.textContaining('Kapha 14'), findsOneWidget);
    // The weights are reconstructed, not CCRAS's licensed table, and the slip has to say so.
    expect(find.textContaining('Provisional'), findsOneWidget);
  });

  testWidgets('slip invents no Prakriti when none was scored', (tester) async {
    // The previous build defaulted the dominant dosha to "Pitta" when nothing was assessed,
    // which put a constitution on a clinical slip that no questionnaire had produced.
    await pumpOnTablet(tester, slipWith({'routing': {'queue': 'General Medicine OPD'}}));
    expect(find.textContaining('Prakriti'), findsNothing);
    expect(find.textContaining('Pitta'), findsNothing);
    expect(find.textContaining('Kapha'), findsNothing);
  });
}
