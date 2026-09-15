import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/models.dart';

enum ConnectionStatus { disconnected, connecting, connected, reconnecting }

class KioskClient extends ChangeNotifier {
  String _host;
  final int _port;
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _pingTimer;
  Timer? _reconnectTimer;

  ConnectionStatus _status = ConnectionStatus.disconnected;
  ConnectionStatus get status => _status;

  String get host => _host;
  set host(String newHost) {
    if (_host != newHost) {
      _sessionId = null;
      _clearPatient();
      _host = newHost;
      reconnect();
    }
  }

  // Current kiosk state from server
  KioskStage _currentStage = KioskStage.language;
  KioskStage get currentStage => _currentStage;

  String _headline = 'अपनी भाषा चुनें / Choose your language';
  String get headline => _headline;

  String _language = 'hi-IN';
  String get language => _language;

  String? _questionId;
  String? _answerUi;
  String? get questionId => _questionId;

  /// 'yes_no', 'faces', 'duration', 'body_map', 'age_bands' - chosen by the server so the tablet,
  /// the browser and the wired panel offer the same control for the same question.
  String? get answerUi => _answerUi;

  List<Map<String, dynamic>> _options = [];
  List<Map<String, dynamic>> get options => _options;

  /// `[answered, total]` for questionnaire stages, as the server counts it.
  List<int>? _progress;
  List<int>? get progress => _progress;

  Map<String, dynamic>? _lastReport;
  Map<String, dynamic>? get lastReport => _lastReport;

  List<Map<String, dynamic>> _redFlags = [];
  List<Map<String, dynamic>> get redFlags => _redFlags;

  bool _isEmergency = false;
  bool get isEmergency => _isEmergency;

  String _lastTranscript = '';
  String get lastTranscript => _lastTranscript;

  bool _isProcessing = false;
  bool get isProcessing => _isProcessing;

  // Stream controller for TTS audio (base64 audio bytes + sample rate)
  final _ttsController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get ttsStream => _ttsController.stream;

  /// Callback when a final speech transcript is received (e.g. from Jetson Whisper)
  ValueChanged<String>? onTranscriptReceived;

  // Public names are used by the connection settings and tests.
  // ignore: prefer_initializing_formals
  KioskClient({String host = '127.0.0.1', int port = 8000})
    // ignore: prefer_initializing_formals
    : _host = host,
      // ignore: prefer_initializing_formals
      _port = port;

  bool _disposed = false;
  int _generation = 0;
  String? _sessionId;
  String? _error;
  String? get error => _error;
  bool _voiceAvailable = false;
  bool get voiceAvailable => _voiceAvailable;
  Timer? _answerTimer;

  void connect() {
    if (_disposed ||
        _status == ConnectionStatus.connected ||
        _status == ConnectionStatus.connecting) {
      return;
    }

    _setStatus(ConnectionStatus.connecting);
    _reconnectTimer?.cancel();
    final generation = ++_generation;
    final uri = Uri(
      scheme: 'ws',
      host: _host,
      port: _port,
      path: '/ws/session',
      queryParameters: _sessionId == null ? null : {'resume': _sessionId!},
    );

    try {
      final channel = WebSocketChannel.connect(uri);
      _channel = channel;
      _subscription = channel.stream.listen(
        (msg) {
          if (!_disposed && generation == _generation) _handleMessage(msg);
        },
        onDone: () {
          if (!_disposed && generation == _generation) _handleDone();
        },
        onError: (err) {
          if (!_disposed && generation == _generation) _handleError(err);
        },
        cancelOnError: true,
      );

      channel.ready
          .timeout(const Duration(seconds: 8))
          .then((_) {
            if (_disposed || generation != _generation) return;
            _setStatus(ConnectionStatus.connected);
            _startPing();
            sendLog('Flutter kiosk connected from client');
          })
          .catchError((err) {
            if (!_disposed && generation == _generation) _handleError(err);
          });
    } catch (e) {
      _handleError(e);
    }
  }

  void _startPing() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      if (_status == ConnectionStatus.connected) {
        // Send lightweight client heartbeat
        send({
          'type': 'client.heartbeat',
          'timestamp': DateTime.now().millisecondsSinceEpoch,
        });
      }
    });
  }

  void _handleMessage(dynamic message) {
    if (message is String) {
      try {
        final data = jsonDecode(message) as Map<String, dynamic>;
        _processServerMessage(data);
      } catch (e) {
        if (kDebugMode) print('Failed to parse WS JSON: $e');
      }
    } else if (message is Uint8List) {
      // Binary audio stream from server
    }
  }

  void _processServerMessage(Map<String, dynamic> msg) {
    final type = msg['type'] as String?;
    if (kDebugMode) debugPrint('WS <- $type');

    switch (type) {
      case 'session.id':
      case 'session.ready':
        _sessionId = msg['session_id'] as String?;
        break;
      case 'configuration.required':
        _voiceAvailable = (msg['missing'] as List? ?? const []).isEmpty;
        notifyListeners();
        break;
      case 'error':
        _error =
            msg['message'] as String? ??
            'The kiosk could not complete this action';
        _isProcessing = false;
        _answerTimer?.cancel();
        notifyListeners();
        break;
      case 'flow.screen':
        final screenData = msg['data'] as Map<String, dynamic>? ?? {};
        final stageStr = screenData['stage'] as String? ?? 'language';
        _currentStage = KioskStageExtension.fromString(stageStr);
        if (_currentStage == KioskStage.language) _clearPatient();
        _answerUi = null;
        _error = null;
        _answerTimer?.cancel();
        if (screenData['report'] is Map<String, dynamic>) {
          _lastReport = screenData['report'] as Map<String, dynamic>;
        }
        _headline = screenData['headline'] as String? ?? _headline;
        _questionId = screenData['question_id'] as String?;
        final rawProgress = screenData['progress'];
        _progress = rawProgress is List
            ? rawProgress.map((value) => (value as num).toInt()).toList()
            : null;
        if (screenData['options'] != null) {
          _options = List<Map<String, dynamic>>.from(screenData['options']);
        } else {
          _options = [];
        }
        if (screenData['alert'] == true ||
            _currentStage == KioskStage.emergency) {
          _isEmergency = true;
        }
        _isProcessing = false;
        notifyListeners();
        break;

      case 'clinical.question':
        _answerTimer?.cancel();
        _error = null;
        _headline = msg['text'] as String? ?? _headline;
        _questionId = msg['id'] as String?;
        // Which pictorial control the server wants drawn for this question.
        _answerUi = msg['answer_ui'] as String?;
        // The clinical question IS the screen, as it is on the wired kiosk. Without this the
        // question was painted onto whatever stage happened to be showing - a red flag question
        // landed on the Ayurveda chooser, which had no options for it, so the patient saw a
        // question with nothing to answer it with.
        _currentStage = KioskStage.interview;
        _isProcessing = false;
        notifyListeners();
        break;

      case 'clinical.turn':
        final turn = msg['data'] as Map<String, dynamic>? ?? {};
        if (turn['next_question'] is String && !_isEmergency) {
          _headline = turn['next_question'] as String;
          _questionId = turn['next_question_id'] as String?;
          _currentStage = KioskStage.interview;
        }
        _answerTimer?.cancel();
        _isProcessing = false;
        notifyListeners();
        break;

      case 'clinical.processing':
        _isProcessing = true;
        notifyListeners();
        break;

      case 'staff.alert':
        _isEmergency = true;
        _currentStage = KioskStage.emergency;
        if (msg['alerts'] != null) {
          _redFlags = List<Map<String, dynamic>>.from(msg['alerts']);
        }
        notifyListeners();
        break;

      case 'flow.report':
        _lastReport = msg['data'] as Map<String, dynamic>?;
        _isProcessing = false;
        notifyListeners();
        break;

      case 'transcript.final':
        _lastTranscript = msg['text'] as String? ?? '';
        notifyListeners();
        if (_lastTranscript.trim().isNotEmpty) {
          onTranscriptReceived?.call(_lastTranscript);
        }
        break;

      case 'tts.start':
      case 'tts.audio':
      case 'tts.cancelled':
      case 'tts.end':
        _ttsController.add(msg);
        break;
    }
  }

  void _handleDone() {
    _setStatus(ConnectionStatus.reconnecting);
    _cleanup();
    _scheduleReconnect();
  }

  void _handleError(dynamic error) {
    if (kDebugMode) print('WS Error: $error');
    _setStatus(ConnectionStatus.reconnecting);
    _cleanup();
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      connect();
    });
  }

  void reconnect() {
    _cleanup();
    connect();
  }

  void _cleanup() {
    ++_generation;
    _answerTimer?.cancel();
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    _subscription?.cancel();
    _channel?.sink.close();
    _subscription = null;
    _channel = null;
    // Reset the status too. connect() refuses to run while the status says "connecting", so a
    // teardown that left it set made reconnect() a no-op: the app dialled the unreachable default
    // host once, stuck at "connecting", and then ignored the address discovery had just found.
    if (_status != ConnectionStatus.disconnected) {
      _setStatus(ConnectionStatus.disconnected);
    }
  }

  void _setStatus(ConnectionStatus status) {
    if (_disposed) return;
    _status = status;
    notifyListeners();
  }

  // Action methods
  void send(Map<String, dynamic> payload) {
    if (_channel != null && _status == ConnectionStatus.connected) {
      _channel!.sink.add(jsonEncode(payload));
    }
  }

  void sendAudio(Uint8List pcm) {
    if (_channel != null && _status == ConnectionStatus.connected) {
      _channel!.sink.add(pcm);
    }
  }

  void _clearPatient() {
    _isEmergency = false;
    _redFlags = [];
    _lastReport = null;
    _lastTranscript = '';
    _questionId = null;
    _answerUi = null;
    _isProcessing = false;
    _progress = null;
    _error = null;
    _options = [];
  }

  void _action(Map<String, dynamic> payload) {
    if (_status != ConnectionStatus.connected) {
      _error = 'Disconnected. Reconnect before answering.';
      notifyListeners();
      return;
    }
    if (_isProcessing) return;
    _error = null;
    _isProcessing = true;
    _answerTimer?.cancel();
    _answerTimer = Timer(const Duration(seconds: 30), () {
      if (_disposed) return;
      _isProcessing = false;
      _error =
          'No response from the kiosk. Check the connection and try again.';
      notifyListeners();
    });
    send(payload);
    notifyListeners();
  }

  void selectLanguage(String code) {
    _language = code.replaceAll('_', '-').split('-').first;
    _action({'type': 'flow.language', 'value': _language});
  }

  void submitAbha(String value) =>
      _action({'type': 'flow.abha', 'value': value});
  void selectWho(String value) => _action({'type': 'flow.who', 'value': value});
  void submitAyurvedaAnswer(String questionId, String value) => _action({
    'type': 'flow.ayurveda',
    'question_id': questionId,
    'value': value,
  });

  /// One command for both halves of the Prakriti stage. The opening screen asks whether the
  /// patient has ever filled the questionnaire and carries no question id; every screen after it
  /// is a question. The server tells them apart the same way.
  void submitPrakritiAnswer(String? questionId, String value) => _action({
    'type': 'flow.prakriti',
    'question_id': ?questionId,
    'value': value,
  });
  void submitTranscript(String text) {
    if (text.trim().isEmpty || _isProcessing) return;
    _lastTranscript = text.trim();
    _action({
      'type': 'transcript.submit',
      'text': text.trim(),
      'language': _language,
    });
  }

  void triggerBargeIn() => send({'type': 'barge_in'});
  void repeatQuestion() => send({'type': 'flow.repeat'});
  void nextStage() => _action({'type': 'flow.next'});
  void backStage() => _action({'type': 'flow.back'});
  void restartSession() {
    _isProcessing = false;
    _action({'type': 'flow.restart'});
  }

  void sendLog(String message) {
    send({'type': 'client.log', 'message': message});
  }

  @override
  void dispose() {
    _disposed = true;
    _cleanup();
    _reconnectTimer?.cancel();
    _ttsController.close();
    super.dispose();
  }
}
