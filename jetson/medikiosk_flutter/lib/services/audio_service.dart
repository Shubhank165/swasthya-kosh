import 'dart:async';
import 'dart:typed_data';
import 'dart:math' as math;

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

/// Microphone capture and speech playback for the kiosk tablet.
///
/// Streams raw PCM to the Jetson rather than using on-device speech recognition. That is not a
/// style preference. `speech_to_text` routes through Google's recogniser, which needs the network
/// unless a language pack happens to be installed, and offline packs for the nine Indian languages
/// this kiosk supports are unreliable and device-dependent. The product promise is that a camp
/// with no uplink still works, and the Jetson already runs whisper.cpp large-v3-turbo on CUDA with
/// a Silero VAD in front of it.
///
/// The wire format is exactly what the server's `run_local_stt` already accepts from the browser
/// and Kivy clients: 16 kHz, mono, signed 16-bit little-endian PCM, as binary WebSocket frames.
/// No server change was needed to accept this client.
class AudioService extends ChangeNotifier {
  static const int sampleRate = 16000;

  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();

  StreamSubscription<Uint8List>? _micSubscription;
  Timer? _resumeTimer;

  /// Watches that PCM is still arriving. Android can end the capture stream on its own - an audio
  /// focus change, or the recorder losing the input device while the kiosk speaks - and the stream
  /// simply completes. Nothing here noticed: `_isCapturing` stayed true, the strip still read
  /// "Mic Listening", and the tablet sent zero bytes to the Jetson. A kiosk that has gone deaf
  /// must say so and try to recover, not keep claiming it is listening.
  Timer? _micWatchdog;
  DateTime? _lastChunkAt;
  int _chunksSinceStart = 0;
  bool _disposed = false;
  bool _wantsCapture = false;
  bool _starting = false;
  bool _restarting = false;
  bool _playing = false;
  bool _temporaryPause = false;
  int _playbackGeneration = 0;
  Future<void> _playbackQueue = Future.value();
  Timer? _retryTimer;
  bool _isAvailable = false;
  bool _isCapturing = false;
  bool _paused = false;
  double _soundLevel = 0.0;
  String _activeLocaleId = 'hi_IN';
  String _status = 'idle';

  bool get isAvailable => _isAvailable;
  bool get isListening => _isCapturing && !_paused && !_playing && !_temporaryPause;
  bool get isPausedTemporarily => _paused || _playing || _temporaryPause;
  double get soundLevel => _soundLevel;
  String get activeLocaleId => _activeLocaleId;
  String get status => _status;

  /// Recognition happens on the Jetson now, so there is no partial hypothesis to show locally.
  /// Kept so the existing status strip compiles and simply stays quiet.
  String get currentWords => '';

  /// Raw PCM destined for the WebSocket. Wired to `KioskClient.sendAudio`.
  ValueChanged<Uint8List>? onPcm;

  /// Retained for callers; the server delivers finished transcripts over the socket.
  ValueChanged<String>? onFinalTranscript;

  AudioService({this.onPcm, this.onFinalTranscript});

  void _setStatus(String value) {
    if (_disposed) return;
    _status = value;
    if (kDebugMode) print('AudioService: $value');
    notifyListeners();
  }

  Future<bool> initialize() async {
    if (kIsWeb ||
        (defaultTargetPlatform != TargetPlatform.android &&
            defaultTargetPlatform != TargetPlatform.iOS)) {
      _setStatus('desktop build; the Jetson uses its own microphone');
      return false;
    }
    try {
      _isAvailable = await _recorder.hasPermission();
    } catch (error) {
      _isAvailable = false;
      _setStatus('microphone check failed: $error');
      return false;
    }
    _setStatus(
      _isAvailable ? 'microphone ready' : 'microphone permission denied',
    );
    return _isAvailable;
  }

  /// Language is chosen on the kiosk screen and pins Whisper server-side, so this only records
  /// what was picked. Kept for callers that still announce a locale change.
  void setLocale(String locale) {
    _activeLocaleId = locale;
  }

  Future<void> startListening({String? localeId}) async {
    if (localeId != null && localeId.isNotEmpty) _activeLocaleId = localeId;
    if (_disposed) return;
    _wantsCapture = true;
    if (_isCapturing || _starting) return;
    _starting = true;
    try {
      if (!_isAvailable && !await initialize()) return;
      if (_disposed || !_wantsCapture) return;
      final stream = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: sampleRate,
          numChannels: 1,
          // Our own prompt playback must not pause Android's recorder.
          audioInterruption: AudioInterruptionMode.none,
          echoCancel: true,
          noiseSuppress: true,
          // Android's voice-communication path gives us its echo canceller. A kiosk speaking
          // through its own speaker will otherwise transcribe its own questions back.
          androidConfig: AndroidRecordConfig(
            audioSource: AndroidAudioSource.voiceCommunication,
          ),
        ),
      );
      if (_disposed || !_wantsCapture) {
        await _recorder.stop();
        return;
      }
      _micSubscription = stream.listen(
        _onChunk,
        onError: (Object error) {
          _setStatus('microphone stream error: $error');
          _restartCapture();
        },
        // The stream ending is the failure that was invisible before.
        onDone: () {
          _isCapturing = false;
          _setStatus('microphone stream ended');
          _restartCapture();
        },
      );
      _isCapturing = true;
      _chunksSinceStart = 0;
      _lastChunkAt = DateTime.now();
      _startWatchdog();
      _setStatus('listening');
    } catch (error) {
      _isAvailable = false;
      _setStatus('microphone start failed: $error');
      _retryTimer?.cancel();
      _retryTimer = Timer(const Duration(seconds: 3), () {
        if (_wantsCapture && !_disposed) startListening();
      });
    } finally {
      _starting = false;
    }
  }

  void _startWatchdog() {
    _micWatchdog?.cancel();
    _micWatchdog = Timer.periodic(const Duration(seconds: 3), (_) {
      if (kDebugMode) {
        debugPrint(
          'mic: capturing=$_isCapturing paused=$_paused chunks=$_chunksSinceStart',
        );
      }
      if (!_isCapturing || _disposed) return;
      final last = _lastChunkAt;
      if (last == null) return;
      if (DateTime.now().difference(last) > const Duration(seconds: 4)) {
        _setStatus('microphone went silent - restarting');
        _restartCapture();
      }
    });
  }

  /// Tear the capture down and start it again. Guarded against re-entry by stopListening()
  /// clearing _isCapturing before startListening() checks it.
  Future<void> _restartCapture() async {
    if (_disposed || !_wantsCapture || _restarting || _starting) return;
    _restarting = true;
    try {
      await _stopCapture();
      if (_wantsCapture && !_disposed) {
        await startListening(localeId: _activeLocaleId);
      }
    } finally {
      _restarting = false;
    }
  }

  void _onChunk(Uint8List chunk) {
    if (_disposed || !_wantsCapture) return;
    _lastChunkAt = DateTime.now();
    _chunksSinceStart++;
    _soundLevel = _level(chunk);
    if (!_paused && !_playing && !_temporaryPause) onPcm?.call(chunk);
    notifyListeners();
  }

  /// Rough level for the VU meter only. Nothing decides anything on it - the Jetson's Silero VAD
  /// owns utterance boundaries, and duplicating that here would give two disagreeing answers.
  double _level(Uint8List bytes) {
    if (bytes.length < 2) return 0;
    final samples = bytes.buffer.asByteData(
      bytes.offsetInBytes,
      bytes.lengthInBytes,
    );
    var sum = 0.0;
    for (var i = 0; i + 1 < bytes.length; i += 2) {
      final sample = samples.getInt16(i, Endian.little).toDouble();
      sum += sample * sample;
    }
    return (math.sqrt(sum / (bytes.length ~/ 2)) / 32768 * 8).clamp(0.0, 1.0);
  }

  Future<void> stopListening() async {
    _wantsCapture = false;
    _retryTimer?.cancel();
    await _stopCapture();
  }

  Future<void> _stopCapture() async {
    _isCapturing = false;
    _micWatchdog?.cancel();
    await _micSubscription?.cancel();
    _micSubscription = null;
    try {
      if (await _recorder.isRecording()) await _recorder.stop();
    } catch (_) {
      // Already stopped.
    }
    _isCapturing = false;
    _setStatus('stopped');
  }

  Future<void> toggleListening() async {
    if (_isCapturing) {
      await stopListening();
    } else {
      await startListening();
    }
  }

  /// Hold the stream while the kiosk is speaking, or while the patient is on a touch-only screen.
  /// Capture keeps running so there is no start-up delay when it resumes.
  void pauseTemporarily(Duration duration) {
    _temporaryPause = true;
    notifyListeners();
    _resumeTimer?.cancel();
    _resumeTimer = Timer(duration, () {
      _temporaryPause = false;
      if (!_disposed) notifyListeners();
    });
  }

  void setPaused(bool value) {
    if (_paused == value) return;
    _paused = value;
    notifyListeners();
  }

  /// Play one chunk of speech from the server. `tts.audio` carries bare PCM at a rate that varies
  /// between Piper and Flite voices, so a WAV header is built in memory for it.
  Future<void> playPcm(Uint8List pcm, int rate) {
    if (_disposed || rate <= 0 || pcm.isEmpty) return Future.value();
    final generation = _playbackGeneration;
    _playbackQueue = _playbackQueue.then((_) async {
      if (_disposed || generation != _playbackGeneration) return;
      _playing = true;
      notifyListeners();
      final completed = Completer<void>();
      final subscription = _player.onPlayerComplete.listen((_) {
        if (!completed.isCompleted) completed.complete();
      });
      try {
        await _player.setAudioContext(AudioContext(
          android: const AudioContextAndroid(
            contentType: AndroidContentType.speech,
            audioFocus: AndroidAudioFocus.none,
          ),
        ));
        await _player.play(
          BytesSource(_wrapWav(pcm, rate)),
          mode: PlayerMode.mediaPlayer,
        );
        // Include actual playback completion so chunks cannot overwrite each other.
        await completed.future.timeout(
          Duration(milliseconds: pcm.length * 500 ~/ rate + 2000),
        );
      } catch (error) {
        if (!_disposed && generation == _playbackGeneration) {
          _setStatus('playback failed: $error');
        }
      } finally {
        await subscription.cancel();
        if (!_disposed && generation == _playbackGeneration) {
          _playing = false;
          pauseTemporarily(const Duration(milliseconds: 250));
        }
      }
    });
    return _playbackQueue;
  }

  Future<void> stopPlayback() async {
    ++_playbackGeneration;
    _playbackQueue = Future.value();
    _playing = false;
    try {
      await _player.stop();
    } catch (_) {}
    if (!_disposed) notifyListeners();
  }

  static Uint8List _wrapWav(Uint8List pcm, int rate) {
    const channels = 1;
    const bits = 16;
    final builder = BytesBuilder();
    void ascii(String value) => builder.add(value.codeUnits);
    void uint32(int value) => builder.add(
      Uint8List(4)..buffer.asByteData().setUint32(0, value, Endian.little),
    );
    void uint16(int value) => builder.add(
      Uint8List(2)..buffer.asByteData().setUint16(0, value, Endian.little),
    );

    ascii('RIFF');
    uint32(36 + pcm.length);
    ascii('WAVE');
    ascii('fmt ');
    uint32(16);
    uint16(1); // PCM
    uint16(channels);
    uint32(rate);
    uint32(rate * channels * bits ~/ 8);
    uint16(channels * bits ~/ 8);
    uint16(bits);
    ascii('data');
    uint32(pcm.length);
    builder.add(pcm);
    return builder.toBytes();
  }

  @override
  void dispose() {
    _disposed = true;
    _wantsCapture = false;
    ++_playbackGeneration;
    _retryTimer?.cancel();
    _resumeTimer?.cancel();
    _micWatchdog?.cancel();
    _micSubscription?.cancel();
    _recorder.dispose();
    _player.dispose();
    super.dispose();
  }
}
