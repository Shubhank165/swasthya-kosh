import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_flutter/models/models.dart';
import 'package:medikiosk_flutter/services/kiosk_client.dart';

Future<void> eventually(bool Function() predicate) async {
  for (var i = 0; i < 100; i++) {
    if (predicate()) return;
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
  fail('Expected state was not reached');
}

void main() {
  late HttpServer server;
  late KioskClient client;
  late WebSocket socket;
  late List<Map<String, dynamic>> commands;
  late List<Uri> connections;
  setUp(() async {
    commands = [];
    connections = [];
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      connections.add(request.uri);
      socket = await WebSocketTransformer.upgrade(request);
      socket.listen((value) {
        if (value is String) commands.add(jsonDecode(value) as Map<String, dynamic>);
      });
    });
    client = KioskClient(host: '127.0.0.1', port: server.port);
    client.connect();
    await eventually(() => client.status == ConnectionStatus.connected);
  });
  tearDown(() async {
    client.dispose();
    await socket.close();
    await server.close(force: true);
  });
  void emit(Map<String, dynamic> event) => socket.add(jsonEncode(event));

  test('waits for server before changing stage and normalizes language', () async {
    client.selectLanguage('hi-IN');
    expect(client.currentStage, KioskStage.language);
    await eventually(() => commands.any((c) => c['type'] == 'flow.language'));
    expect(commands.last['value'], 'hi');
    emit({'type': 'flow.screen', 'data': {'stage': 'abha', 'headline': 'Card'}});
    await eventually(() => client.currentStage == KioskStage.abha);
  });
  test('uses clinical.turn question when server omits question event', () async {
    emit({'type': 'clinical.question', 'id': 'ask_bleeding', 'text': 'Bleeding?'});
    await eventually(() => client.questionId == 'ask_bleeding');
    client.submitTranscript('no');
    expect(client.questionId, 'ask_bleeding');
    expect(client.isProcessing, isTrue);
    emit({'type': 'clinical.turn', 'data': {
      'next_question_id': 'ask_age', 'next_question': 'Age?',
    }});
    await eventually(() => client.questionId == 'ask_age');
    expect(client.headline, 'Age?');
    expect(client.isProcessing, isFalse);
  });
  test('does not infer emergency from negated typed keywords', () async {
    client.submitTranscript('I am not unconscious');
    expect(client.isEmergency, isFalse);
  });
  test('double tap sends only one pending answer', () async {
    client.submitTranscript('no');
    client.submitTranscript('no');
    await eventually(() => commands.any((c) => c['type'] == 'transcript.submit'));
    expect(commands.where((c) => c['type'] == 'transcript.submit'), hasLength(1));
  });
  test('the prakriti stage is recognised rather than falling back to language', () async {
    // KioskStageExtension.fromString defaults to `language` for anything it does not know, so a
    // stage the server sends but Dart has not been taught bounces the patient back to the
    // language screen mid-intake instead of showing the question.
    emit({'type': 'flow.screen', 'data': {
      'stage': 'prakriti',
      'gate': true,
      'headline': 'Have you filled this before?',
      'options': [
        {'value': 'yes', 'label': 'Yes', 'icon': 'check'},
        {'value': 'no', 'label': 'No', 'icon': 'cross'},
      ],
    }});
    await eventually(() => client.currentStage == KioskStage.prakriti);
    expect(client.headline, 'Have you filled this before?');
    expect(client.options, hasLength(2));
  });
  test('the prakriti gate answers without a question id, questions with one', () async {
    // The server tells the opening gate from a question by whether question_id is present, so
    // the client must not invent one for the gate.
    client.submitPrakritiAnswer(null, 'no');
    await eventually(() => commands.any((c) => c['type'] == 'flow.prakriti'));
    final gate = commands.lastWhere((c) => c['type'] == 'flow.prakriti');
    expect(gate.containsKey('question_id'), isFalse);
    expect(gate['value'], 'no');

    // The next screen clears the double-tap guard in _action; without it the second answer is
    // dropped, which is the same protection that stops a double tap sending two answers.
    emit({'type': 'flow.screen', 'data': {
      'stage': 'prakriti',
      'question_id': 'pk_sleep_hours',
      'headline': 'How many hours do you sleep?',
      'options': [
        {'value': 'under_6', 'label': 'Less than 6 hours', 'icon': 'sleep'},
      ],
    }});
    await eventually(() => client.questionId == 'pk_sleep_hours');

    client.submitPrakritiAnswer('pk_sleep_hours', 'under_6');
    await eventually(() =>
        commands.where((c) => c['type'] == 'flow.prakriti').length == 2);
    final answer = commands.lastWhere((c) => c['type'] == 'flow.prakriti');
    expect(answer['question_id'], 'pk_sleep_hours');
    expect(answer['value'], 'under_6');
  });
  test('does not fabricate a report when advancing', () async {
    emit({'type': 'flow.screen', 'data': {'stage': 'documents'}});
    await eventually(() => client.currentStage == KioskStage.documents);
    client.nextStage();
    expect(client.currentStage, KioskStage.documents);
    expect(client.lastReport, isNull);
  });
  test('propagates cancellation and errors, clearing pending state', () async {
    final events = <Map<String, dynamic>>[];
    final subscription = client.ttsStream.listen(events.add);
    client.submitTranscript('no');
    emit({'type': 'tts.cancelled', 'reason': 'next_question'});
    emit({'type': 'error', 'stage': 'clinical', 'message': 'Please retry'});
    await eventually(() => client.error != null && events.isNotEmpty);
    expect(client.isProcessing, isFalse);
    expect(events.single['type'], 'tts.cancelled');
    await subscription.cancel();
  });
  test('reconnect sends the session id and closes the old socket', () async {
    emit({'type': 'session.id', 'session_id': 'test-session'});
    await Future<void>.delayed(const Duration(milliseconds: 30));
    final previous = socket;
    client.reconnect();
    await eventually(() => connections.length == 2 && client.status == ConnectionStatus.connected);
    expect(connections.last.queryParameters['resume'], 'test-session');
    await eventually(() => previous.readyState == WebSocket.closed);
  });
  test('new language screen clears previous patient report and alert', () async {
    emit({'type': 'staff.alert', 'alerts': <Map<String, dynamic>>[]});
    emit({'type': 'flow.report', 'data': {'patient': 'synthetic'}});
    await eventually(() => client.lastReport != null);
    emit({'type': 'flow.screen', 'data': {'stage': 'language', 'headline': 'Choose',
      'options': [{'value': 'en', 'label': 'English'}]}});
    await eventually(() => client.currentStage == KioskStage.language);
    expect(client.isEmergency, isFalse);
    expect(client.lastReport, isNull);
    expect(client.options, hasLength(1));
  });
}
