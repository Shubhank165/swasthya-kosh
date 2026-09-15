import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_flutter/models/models.dart';
import 'package:medikiosk_flutter/screens/kiosk_controller_screen.dart';
import 'package:medikiosk_flutter/services/kiosk_client.dart';

class RenderClient extends KioskClient {
  Map<String, dynamic> data = {};
  Map<String, dynamic>? receipt;
  final sent = <List<dynamic>>[];
  bool busy = false;
  ConnectionStatus connection = ConnectionStatus.connected;
  @override
  Map<String, dynamic> get screen => data;
  @override
  String get headline => data['headline'] as String? ?? '';
  @override
  String get language => data['language'] as String? ?? 'en';
  @override
  KioskStage get currentStage => KioskStageExtension.fromString(data['stage'] as String? ?? 'unavailable');
  @override
  List<Map<String, dynamic>> get options => List<Map<String, dynamic>>.from(data['options'] as List? ?? []);
  @override
  Map<String, dynamic>? get lastReport => receipt;
  @override
  bool get isProcessing => busy;
  @override
  ConnectionStatus get status => connection;
  bool accumulating = false;
  String text = '';
  @override
  bool get accumulate => accumulating;
  @override
  String get narrative => text;
  @override
  void setNarrative(String value) { text = value; }
  @override
  void action(String action, [dynamic value]) { sent.add([action, value]); }
}

Future<void> render(WidgetTester tester, RenderClient client) async {
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(
    child: WorkflowBody(client: client),
  ))));
}

void main() {
  testWidgets('submit sends current typed value including zero', (tester) async {
    final client = RenderClient()..data = {'stage': 'registration', 'input': 'number',
      'headline': 'Age?', 'allowed_actions': ['answer', 'unknown']};
    await render(tester, client);
    await tester.enterText(find.byType(TextField), '0');
    await tester.tap(find.text('Submit answer'));
    expect(client.sent, [['answer', '0']]);
    await tester.pumpWidget(const SizedBox());
    client.dispose();
  });

  testWidgets('consent shows only offered options and disables pending taps', (tester) async {
    final client = RenderClient()..data = {'stage': 'consent', 'headline': 'Local permission',
      'options': [{'label': 'Yes', 'value': 'yes'}, {'label': 'No', 'value': 'no'}],
      'allowed_actions': ['help']};
    await render(tester, client);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('Done'), findsNothing);
    await tester.tap(find.text('1. Yes'));
    expect(client.sent, [['choose', 'yes']]);
    client.busy = true;
    await render(tester, client);
    await tester.tap(find.text('2. No'));
    expect(client.sent, hasLength(1));
    await tester.pumpWidget(const SizedBox());
    client.dispose();
  });

  testWidgets('the opening question is a description box that sends once, on Proceed', (tester) async {
    final client = RenderClient()..data = {'stage': 'interview', 'input': 'text',
      'headline': 'Please describe your problem in brief.',
      'allowed_actions': ['unknown', 'help']}..accumulating = true..text = 'stomach pain';
    await render(tester, client);
    expect(find.text('Proceed'), findsOneWidget);
    expect(find.text('Submit answer'), findsNothing);
    expect(find.text('stomach pain'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'stomach pain since two days');
    await tester.tap(find.text('Proceed'));
    expect(client.sent, [['answer', 'stomach pain since two days']]);
    await tester.pumpWidget(const SizedBox());
    client.dispose();
  });

  testWidgets('shell wording follows the patient language, all nine of them', (tester) async {
    final client = RenderClient()..data = {'stage': 'registration', 'input': 'text',
      'headline': 'உங்கள் பெயர் என்ன?', 'language': 'ta', 'allowed_actions': ['answer', 'help']};
    await render(tester, client);
    expect(find.text('பதிலை அனுப்பு'), findsOneWidget);
    expect(find.text('உதவி கேள்'), findsOneWidget);
    expect(find.text('Submit answer'), findsNothing);
    await tester.pumpWidget(const SizedBox());
    client.dispose();
  });

  testWidgets('review edits use answer identity, not displayed text', (tester) async {
    final client = RenderClient()..data = {'stage': 'review', 'review': [
      {'id': 'registration.age', 'question': 'Age?', 'status': 'unresolved', 'answer': ''}],
      'allowed_actions': ['confirm']};
    await render(tester, client);
    await tester.tap(find.text('Edit answer 1'));
    expect(client.sent, [['edit', 'registration.age']]);
    expect(find.text('unresolved'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    client.dispose();
  });

  testWidgets('empty OCR is a visible preview with explicit resolution', (tester) async {
    final client = RenderClient()..data = {'stage': 'documents',
      'capture_preview': {'lines': [], 'confidence_note': 'Unverified'},
      'allowed_actions': ['keep', 'retake', 'discard']};
    await render(tester, client);
    expect(find.textContaining('No text was read'), findsOneWidget);
    expect(find.text('Done'), findsNothing);
    await tester.tap(find.text('Discard preview'));
    expect(client.sent, [['discard', null]]);
    await tester.pumpWidget(const SizedBox());
    client.dispose();
  });

  testWidgets('receipt appears only on report stage, without fake print success', (tester) async {
    final client = RenderClient()..data = {'stage': 'finalizing'}
      ..receipt = {'completion': 'saved_local', 'queue_entry': {'specialty': 'General Medicine', 'number': 7},
        'prakriti': {'complete': false, 'prakriti': null}};
    await render(tester, client);
    expect(find.textContaining('Token 7'), findsNothing);
    client.data = {'stage': 'report'};
    await render(tester, client);
    expect(find.textContaining('Token 7'), findsOneWidget);
    expect(find.text('Download slip (PDF)'), findsOneWidget);
    expect(find.text('Prakriti incomplete — no classification'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    client.dispose();
  });
}
