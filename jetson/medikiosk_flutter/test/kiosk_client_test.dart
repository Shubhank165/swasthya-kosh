import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_flutter/models/models.dart';
import 'package:medikiosk_flutter/services/kiosk_client.dart';

Future<void> eventually(bool Function() predicate) async {
  for (var i = 0; i < 200; i++) {
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
  late List<String?> protocols;
  late int binaryFrames;
  var revision = 1;
  const id = 'synthetic-session';
  const token = 'synthetic-resume-capability-not-an-identity';
  void emit(Map<String, dynamic> event) => socket.add(jsonEncode({'session_id': id, 'revision': revision, ...event}));

  setUp(() async {
    commands = []; connections = []; protocols = []; binaryFrames = 0; revision = 1;
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      connections.add(request.uri);
      protocols.add(request.headers.value('sec-websocket-protocol'));
      socket = await WebSocketTransformer.upgrade(request, protocolSelector: (_) => 'medikiosk.v2');
      socket.listen((value) {
        if (value is String) commands.add(jsonDecode(value) as Map<String, dynamic>);
        if (value is List<int>) binaryFrames++;
      });
      emit({'type': 'session.id', 'session_token': token});
      emit({'type': 'flow.screen', 'data': {'stage': 'language', 'headline': 'Choose', 'language': 'en'}});
      emit({'type': 'configuration.required', 'missing': []});
    });
    client = KioskClient(host: '127.0.0.1', port: server.port);
    client.connect();
    await eventually(() => client.status == ConnectionStatus.connected && client.voiceAvailable);
  });
  tearDown(() async { client.dispose(); await socket.close(); await server.close(force: true); });

  test('language action is owned and stage changes only on server snapshot', () async {
    client.selectLanguage('hi-IN');
    expect(client.currentStage, KioskStage.language);
    await eventually(() => commands.isNotEmpty);
    expect(commands.single, containsPair('type', 'flow.action'));
    expect(commands.single, containsPair('action', 'choose'));
    expect(commands.single['value'], 'hi');
    expect(commands.single['session_id'], id);
    expect(commands.single['revision'], 1);
    emit({'type': 'flow.screen', 'data': {'stage': 'who', 'language': 'hi', 'headline': 'Who?'}});
    await eventually(() => client.currentStage == KioskStage.who);
    expect(client.language, 'hi');
    expect(client.isProcessing, isTrue); // A screen does not acknowledge an action.
    emit({'type': 'flow.ack', 'action_id': commands.single['action_id']});
    await eventually(() => !client.isProcessing);
  });

  test('all protocol stages are recognized and unknown fails closed', () {
    for (final stage in ['consent', 'registration', 'hub', 'review', 'finalizing', 'declined']) {
      expect(KioskStageExtension.fromString(stage).nameString, stage);
    }
    expect(KioskStageExtension.fromString('newer-unsupported-stage'), KioskStage.unavailable);
  });

  test('double tap sends one action and preserves zero', () async {
    client.action('answer', 0); client.action('answer', 0);
    await eventually(() => commands.isNotEmpty);
    expect(commands, hasLength(1));
    expect(commands.single['value'], 0);
  });

  test('stale patient and prompt events do not alter the screen', () async {
    revision = 5;
    emit({'type': 'clinical.question', 'id': 'ask_age', 'text': 'Age?'});
    await eventually(() => client.questionId == 'ask_age');
    emit({'type': 'flow.screen', 'revision': 2, 'data': {'stage': 'report'}});
    emit({'type': 'flow.screen', 'session_id': 'other-patient', 'data': {'stage': 'report'}});
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(client.currentStage, KioskStage.interview);
    expect(client.headline, 'Age?');
    client.submitTranscript('forty');
    await eventually(() => commands.isNotEmpty);
    expect(commands.single['question_id'], 'ask_age');
    expect(commands.single['revision'], 5);
  });

  test('clinical questions retain server actions and readback decisions', () async {
    revision = 2;
    emit({'type': 'clinical.question', 'id': 'ask_duration', 'text': 'How long?',
      'allowed_actions': ['answer', 'withdraw', 'repeat']});
    await eventually(() => client.questionId == 'ask_duration');
    expect(client.screen['allowed_actions'], ['answer', 'withdraw', 'repeat']);
    revision = 3;
    emit({'type': 'flow.screen', 'data': {'stage': 'interview', 'input': 'touch',
      'headline': 'I heard five days. Is this correct?', 'question_id': 'ask_duration',
      'options': [{'value': 'yes', 'label': 'Yes'}, {'value': 'no', 'label': 'No'}],
      'allowed_actions': ['repeat', 'cancel']}});
    await eventually(() => client.options.length == 2);
    client.action('choose', 'yes');
    await eventually(() => commands.isNotEmpty);
    expect(commands.single['question_id'], 'ask_duration');
    expect(commands.single['revision'], 3);
    expect(commands.single['value'], 'yes');
  });

  test('speech is informational and never dispatched twice on tablet', () async {
    emit({'type': 'transcript.final', 'text': 'yes'});
    await eventually(() => client.lastTranscript == 'yes');
    expect(commands, isEmpty);
  });

  test('help request is neither emergency nor staff acknowledgment', () async {
    emit({'type': 'staff.alert', 'status': 'requested', 'acknowledged': false});
    await eventually(() => client.error != null);
    expect(client.isEmergency, isFalse);
    expect(client.error, contains('not yet acknowledged'));
  });

  test('done and uncommitted report never fabricate completion', () async {
    emit({'type': 'flow.screen', 'data': {'stage': 'documents'}});
    await eventually(() => client.currentStage == KioskStage.documents);
    client.nextStage();
    emit({'type': 'flow.report', 'data': {'completion': 'finalizing'}});
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(client.currentStage, KioskStage.documents);
    expect(client.lastReport, isNull);
    emit({'type': 'flow.report', 'data': {'completion': 'saved_local', 'encounter_id': id}});
    await eventually(() => client.lastReport != null);
    expect(client.currentStage, KioskStage.documents); // still awaiting screen
  });

  test('reconnect uses subprotocol capability and retries exact pending envelope', () async {
    client.action('choose', 'en');
    await eventually(() => commands.isNotEmpty);
    final pending = Map<String, dynamic>.from(commands.single);
    final previous = socket;
    client.reconnect();
    await eventually(() => connections.length == 2 && commands.length == 2);
    expect(connections.last.query, isEmpty);
    expect(protocols.last, contains('resume.$token'));
    expect(commands.last, pending);
    await eventually(() => previous.readyState == WebSocket.closed);
  });

  test('idle warning is shown and idle close forgets the patient capability', () async {
    emit({'type': 'flow.screen', 'data': {'stage': 'consent', 'headline': 'Consent', 'language': 'en'}});
    emit({'type': 'session.idle', 'remaining': 60});
    await eventually(() => (client.error ?? '').contains('more time'));
    expect(client.currentStage, KioskStage.consent);
    await socket.close(4408, 'Idle');
    await eventually(() => connections.length == 2 && client.status == ConnectionStatus.connected);
    expect(protocols.last, isNot(contains('resume.')));
    expect(client.currentStage, KioskStage.language);
    expect(client.error, isNull);
  });
  test('the description accumulates speech and sends once on Proceed', () async {
    emit({'type': 'clinical.question', 'id': 'ask_complaint', 'text': 'Describe your problem', 'accumulate': true,
      'allowed_actions': ['unknown']});
    emit({'type': 'transcript.final', 'text': 'stomach pain', 'accumulate': true});
    emit({'type': 'transcript.final', 'text': 'since two days', 'accumulate': true});
    await eventually(() => client.narrative == 'stomach pain since two days');
    expect(client.accumulate, isTrue);
    expect(commands, isEmpty, reason: 'nothing is dispatched until the patient proceeds');
    client.submitNarrative();
    await eventually(() => commands.length == 1);
    expect(commands.single['action'], 'answer');
    expect(commands.single['value'], 'stomach pain since two days');
    expect(commands.single['question_id'], 'ask_complaint');
    // The next, ordinary question clears the box.
    emit({'type': 'clinical.question', 'id': 'ask_severity', 'text': 'How bad?', 'allowed_actions': ['answer']});
    await eventually(() => !client.accumulate);
    expect(client.narrative, isEmpty);
  });

  test('audio is epoch-bound and stopped until actual playback ends', () async {
    client.sendAudio(Uint8List(32));
    await eventually(() => binaryFrames == 1);
    expect(commands.first['type'], 'audio.start');
    client.playbackState(true);
    client.sendAudio(Uint8List(32));
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(binaryFrames, 1);
    emit({'type': 'tts.end'}); // synthesis completion cannot release actual playback.
    await Future<void>.delayed(const Duration(milliseconds: 30));
    client.sendAudio(Uint8List(32));
    expect(binaryFrames, 1);
    client.playbackState(false);
    client.sendAudio(Uint8List(32));
    await eventually(() => binaryFrames == 2);
    expect(commands.where((c) => c['type'] == 'audio.start'), hasLength(2));
  });

  test('restart clears previous patient receipt only after new identity', () async {
    emit({'type': 'flow.report', 'data': {'completion': 'saved_local'}});
    await eventually(() => client.lastReport != null);
    client.restartSession();
    expect(client.lastReport, isNotNull);
    emit({'type': 'session.id', 'session_id': 'new-session', 'revision': 0, 'session_token': 'new-capability'});
    await eventually(() => client.sessionId == 'new-session');
    expect(client.lastReport, isNull);
  });
}
