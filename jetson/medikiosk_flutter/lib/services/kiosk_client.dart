import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/models.dart';

enum ConnectionStatus { disconnected, connecting, connected, reconnecting }

/// The tablet renders acknowledged backend state; it never walks stages locally.
class KioskClient extends ChangeNotifier {
  String _host;
  final int _port;
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _reconnectTimer;
  Timer? _answerTimer;
  bool _disposed = false;
  int _generation = 0;
  String? _sessionId;
  String? _token;
  int _revision = 0;
  String? _captureEpoch;
  Map<String, dynamic>? _pending;
  ConnectionStatus _status = ConnectionStatus.disconnected;
  Map<String, dynamic> _screen = {'stage': 'language', 'headline': 'Connecting to local kiosk…'};
  String? _questionId;
  String? _answerUi;
  String? _error;
  String _language = 'en';
  String _lastTranscript = '';
  // The opening question collects a free description: speech is appended here instead of
  // being dispatched, until the patient presses Proceed.
  bool _accumulate = false;
  String _narrative = '';
  bool _voiceAvailable = false;
  bool _processing = false;
  bool _playing = false;
  Map<String, dynamic>? _lastReport;
  List<Map<String, dynamic>> _redFlags = [];
  final _ttsController = StreamController<Map<String, dynamic>>.broadcast();
  final _deviceController = StreamController<Map<String, dynamic>>.broadcast();

  // Public constructor names are part of the connection settings API.
  // ignore: prefer_initializing_formals
  KioskClient({String host = '127.0.0.1', int port = 8000}) : _host = host, _port = port;

  String get host => _host;
  set host(String value) {
    if (value == _host) return;
    _host = value;
    _sessionId = _token = null;
    _pending = null;
    _clearPatient();
    reconnect();
  }
  ConnectionStatus get status => _status;
  String? get sessionId => _sessionId;
  int get revision => _revision;
  String get epoch => '$_sessionId:$_revision';
  Map<String, dynamic> get screen => Map.unmodifiable(_screen);
  KioskStage get currentStage => KioskStageExtension.fromString(_screen['stage'] as String? ?? 'unavailable');
  String get headline => _screen['headline'] as String? ?? '';
  String get language => _language;
  String? get questionId => _questionId;
  String? get answerUi => _answerUi;
  String? get error => _error;
  bool get voiceAvailable => _voiceAvailable;
  bool get isProcessing => _processing || _pending != null;
  bool get isEmergency => currentStage == KioskStage.emergency;
  String get lastTranscript => _lastTranscript;
  bool get accumulate => _accumulate;
  String get narrative => _narrative;
  void setNarrative(String text) { _narrative = text; notifyListeners(); }
  // Reads the getter, not the field, so a subclass presenting its own text (tests) sends it.
  void submitNarrative() { if (narrative.trim().isNotEmpty) action('answer', narrative.trim()); }
  Map<String, dynamic>? get lastReport => _lastReport;
  List<Map<String, dynamic>> get redFlags => _redFlags;
  List<Map<String, dynamic>> get options => List<Map<String, dynamic>>.from(_screen['options'] as List? ?? []);
  List<int>? get progress => (_screen['progress'] as List?)?.map((v) => (v as num).toInt()).toList();
  Stream<Map<String, dynamic>> get ttsStream => _ttsController.stream;
  Stream<Map<String, dynamic>> get deviceStream => _deviceController.stream;
  Map<String, String> get scanHeaders => {
    'X-Kiosk-Session': ?_sessionId,
    'X-Kiosk-Token': ?_token,
    'X-Kiosk-Revision': '$_revision',
  };

  void connect() {
    if (_disposed || _status == ConnectionStatus.connected || _status == ConnectionStatus.connecting) return;
    _reconnectTimer?.cancel();
    _setStatus(ConnectionStatus.connecting);
    final generation = ++_generation;
    final uri = Uri(scheme: 'ws', host: _host, port: _port, path: '/ws/session');
    try {
      final channel = WebSocketChannel.connect(uri, protocols: ['medikiosk.v2', if (_token != null) 'resume.$_token']);
      _channel = channel;
      _subscription = channel.stream.listen((message) {
        if (!_disposed && generation == _generation && message is String) {
          try {
            _process(jsonDecode(message) as Map<String, dynamic>);
          } catch (_) {
            _error = 'Invalid response from the local kiosk.';
            notifyListeners();
          }
        }
      }, onDone: () {
        if (_disposed || generation != _generation) return;
        final code = channel.closeCode;
        _cleanup();
        if (code == 4408) {
          // Privacy timeout: the patient walked away. Forget their capability and start fresh.
          _sessionId = _token = null;
          _pending = null;
          _clearPatient();
          connect();
          return;
        }
        if (code == 4404 || code == 4409) {
          _error = code == 4409 ? 'This session is open on another connection.' : 'This session cannot be resumed. Ask staff for help.';
          notifyListeners();
          return;
        }
        _scheduleReconnect();
      }, onError: (_) {
        if (_disposed || generation != _generation) return;
        _cleanup();
        _scheduleReconnect();
      });
      channel.ready.timeout(const Duration(seconds: 8)).then((_) {
        if (!_disposed && generation == _generation) _setStatus(ConnectionStatus.connected);
      }).catchError((_) {
        if (!_disposed && generation == _generation) {
          _cleanup();
          _scheduleReconnect();
        }
      });
    } catch (_) {
      _cleanup();
      _scheduleReconnect();
    }
  }

  void _process(Map<String, dynamic> msg) {
    final type = msg['type'];
    final id = msg['session_id'] as String?;
    if (type == 'session.id') {
      if (id == null || msg['session_token'] is! String) return;
      if (_sessionId != id) {
        _clearPatient();
        _pending = null;
      }
      _sessionId = id;
      _token = msg['session_token'] as String;
      _revision = (msg['revision'] as num).toInt();
    } else {
      if (id != _sessionId || _sessionId == null) return;
      final revision = (msg['revision'] as num?)?.toInt();
      if (revision == null || revision < _revision) return;
      if (revision != _revision) _captureEpoch = null;
      _revision = revision;
    }
    switch (type) {
      case 'configuration.required':
        _voiceAvailable = (msg['missing'] as List? ?? ['unknown']).isEmpty;
        // A lost acknowledgment reuses the exact action id and body, never a new action.
        if (_pending != null) send(_pending!);
        break;
      case 'flow.ack':
        if (_pending?['action_id'] == msg['action_id']) {
          _pending = null;
          _processing = false;
          _answerTimer?.cancel();
          _error = null;
        }
        break;
      case 'error':
        _error = msg['message'] as String? ?? 'Action failed. Please ask staff for help.';
        if (msg['action_id'] == _pending?['action_id']) {
          _pending = null;
          _processing = false;
          _answerTimer?.cancel();
        }
        if (msg['stage'] == 'tts') _ttsController.add({...msg, 'type': 'tts.cancelled'});
        break;
      case 'flow.screen':
        _screen = Map<String, dynamic>.from(msg['data'] as Map);
        if (currentStage == KioskStage.language) {
          _lastReport = null;
          _redFlags = [];
          _lastTranscript = '';
        }
        _language = _screen['language'] as String? ?? _language;
        _questionId = _screen['question_id'] as String?;
        _answerUi = null;
        _processing = false;
        _captureEpoch = null;
        break;
      case 'clinical.question':
        _screen = {..._screen, 'stage': 'interview', 'headline': msg['text'], 'input': 'text', 'options': [],
          'allowed_actions': msg['allowed_actions'] is List ? List<String>.from(msg['allowed_actions']) :
            ['answer', 'unknown', 'refuse', 'repeat', 'help', 'restart', 'slower', 'more_time', 'cancel']};
        _questionId = msg['id'] as String?;
        _answerUi = msg['answer_ui'] as String?;
        _accumulate = msg['accumulate'] == true;
        if (!_accumulate) _narrative = '';
        _processing = false;
        break;
      case 'clinical.processing':
        _processing = true;
        break;
      case 'clinical.turn':
        _processing = false;
        break;
      case 'session.idle':
        _error = 'Still there? Say "more time" or touch the screen to continue.';
        break;
      case 'staff.alert':
        if (msg['alerts'] is List) _redFlags = List<Map<String, dynamic>>.from(msg['alerts']);
        // A help request is not an emergency screen or staff acknowledgment.
        _error = 'Help requested; not yet acknowledged. Please seek staff directly.';
        break;
      case 'flow.report':
        final report = msg['data'];
        if (report is Map<String, dynamic> && report['completion'] == 'saved_local') _lastReport = report;
        break;
      case 'transcript.final':
        _lastTranscript = msg['text'] as String? ?? '';
        if (msg['accumulate'] == true && _lastTranscript.isNotEmpty) {
          // Fills the description box as the patient speaks; nothing is sent until Proceed.
          _narrative = _narrative.isEmpty ? _lastTranscript : '$_narrative $_lastTranscript';
        }
        // Otherwise informational only: the backend already dispatched this transcript.
        break;
      case 'device.action':
        _deviceController.add(msg);
        break;
      case 'tts.start':
      case 'tts.audio':
      case 'tts.end':
      case 'tts.cancelled':
        _captureEpoch = null;
        _ttsController.add(msg);
        break;
    }
    notifyListeners();
  }

  void action(String action, [dynamic value]) {
    if (_status != ConnectionStatus.connected || _sessionId == null || _pending != null) return;
    final random = Random.secure();
    _pending = {'type': 'flow.action', 'session_id': _sessionId, 'revision': _revision,
      'action_id': List.generate(16, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join(),
      'action': action, 'value': value, 'question_id': _questionId};
    _error = null;
    _answerTimer?.cancel();
    _answerTimer = Timer(const Duration(seconds: 30), () {
      if (_disposed || _pending == null) return;
      _error = 'Waiting for saved acknowledgment. Reconnect to retry safely.';
      notifyListeners();
    });
    send(_pending!);
    notifyListeners();
  }

  void send(Map<String, dynamic> payload) {
    if (_status == ConnectionStatus.connected) _channel?.sink.add(jsonEncode(payload));
  }

  void playbackState(bool playing) {
    _playing = playing;
    _captureEpoch = null;
    send({'type': 'playback.state', 'session_id': _sessionId, 'revision': _revision, 'playing': playing});
  }

  void sendAudio(Uint8List pcm) {
    if (_status != ConnectionStatus.connected || !_voiceAvailable || _playing || isProcessing || _sessionId == null) return;
    if (_captureEpoch != epoch) {
      send({'type': 'audio.start', 'session_id': _sessionId, 'revision': _revision});
      _captureEpoch = epoch;
    }
    _channel?.sink.add(pcm);
  }

  void selectLanguage(String code) => action('choose', code.replaceAll('_', '-').split('-').first);
  void submitAbha(String value) => action(value.isEmpty ? 'skip' : 'answer', value);
  void selectWho(String value) => action('choose', value);
  void submitAyurvedaAnswer(String questionId, String value) => action('choose', value);
  void submitPrakritiAnswer(String? questionId, String value) => action('choose', value);
  void submitTranscript(String text) { if (text.trim().isNotEmpty) action('answer', text.trim()); }
  void repeatQuestion() => action('repeat');
  void nextStage() => action('done');
  void backStage() => action('back');
  void restartSession() => action('restart');

  void _clearPatient() {
    _screen = {'stage': 'language', 'headline': 'Connecting to local kiosk…'};
    _lastReport = null;
    _redFlags = [];
    _lastTranscript = _narrative = '';
    _accumulate = false;
    _questionId = _answerUi = _error = null;
    _processing = false;
    _captureEpoch = null;
  }
  void _setStatus(ConnectionStatus status) {
    _status = status;
    if (!_disposed) notifyListeners();
  }
  void _scheduleReconnect() {
    _setStatus(ConnectionStatus.reconnecting);
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), connect);
  }
  void reconnect() { _cleanup(); connect(); }
  void _cleanup() {
    ++_generation;
    _voiceAvailable = false;
    _captureEpoch = null;
    _playing = false;
    _answerTimer?.cancel();
    _reconnectTimer?.cancel();
    _subscription?.cancel();
    _channel?.sink.close();
    _subscription = null;
    _channel = null;
    _setStatus(ConnectionStatus.disconnected);
  }
  @override
  void dispose() {
    _disposed = true;
    _cleanup();
    _ttsController.close();
    _deviceController.close();
    super.dispose();
  }
}
