/// Mic -> text, entirely on the device — 2/3 §16.
///
/// `record` opens the microphone at 16 kHz and buffers PCM in memory.
/// `sherpa_onnx` turns the samples into text. **Neither writes the audio
/// anywhere and nothing sends it** — the bytes live in memory for the few
/// seconds a patient is speaking and are gone when [stop] returns. The model
/// ships in the APK, so this feature touches no network at all.
///
/// Recognition runs in a **background isolate**. Whisper-tiny on a mid-range
/// phone is a two-to-four second job that pins a core; on the UI isolate that
/// is a frozen screen and a patient who thinks the app has hung. The isolate is
/// spawned once, keeps the model warm, and the UI isolate only ever sends it a
/// `Float32List` and awaits a string.
///
/// Like the backend's Gemini adapter, this module is exercised by hand on a
/// device rather than in CI: it needs a real microphone and a real model, and
/// the unit tests cover the parts that do not — the matcher and the button's
/// guards. Every call here fails soft: no permission, no model, no engine, and
/// the caller gets an empty transcript and the patient uses touch.
library;

import 'dart:async';
import 'dart:isolate';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';
import 'package:sherpa_onnx/sherpa_onnx.dart' as sherpa;

import 'asr_models.dart';

/// One [Transcriber] for the app — it holds the recogniser isolate and,
/// briefly, a mic stream, neither of which should be duplicated per screen.
final transcriberProvider = Provider<Transcriber>((ref) {
  final t = Transcriber();
  ref.onDispose(t.dispose);
  return t;
});

const int _sampleRate = 16000;

/// A short spoken answer, transcribed offline.
class Transcriber {
  Transcriber({AudioRecorder? recorder, AsrModelStore? models})
      : _recorder = recorder ?? AudioRecorder(),
        _models = models ?? AsrModelStore();

  final AudioRecorder _recorder;
  final AsrModelStore _models;

  _AsrIsolate? _engine;
  String? _engineLanguage;

  final List<int> _pcm = <int>[];
  StreamSubscription<Uint8List>? _sub;

  /// True when the device can capture PCM and [language]'s model is on disk, so
  /// the mic button can show. **Never prompts for the microphone** — that
  /// happens on the first tap, in [start] — and never copies the model;
  /// [ensureModel] does that. Fails soft: no recorder plugin (or none in a
  /// test) reads as "not ready".
  Future<bool> isReady(String language) async {
    try {
      if (!await _recorder.isEncoderSupported(AudioEncoder.pcm16bits)) {
        return false;
      }
      return await _models.installed(language) != null;
    } on Object {
      return false;
    }
  }

  /// Copy [language]'s model out of the bundled assets if it is not on disk
  /// yet. Returns whether it is now present. No network, no prompt; cheap and
  /// idempotent after the first call. Safe to call at launch to warm it.
  Future<bool> ensureModel(String language) async {
    try {
      return await _models.ensureInstalled(language) != null;
    } on Object catch (e) {
      debugPrint('ensureModel failed: $e');
      return false;
    }
  }

  /// Spin up the recogniser isolate for [language] and load the model into it,
  /// if that has not happened already. Returns whether the engine is ready.
  /// The first call pays ~1–2 s to build the recogniser; later calls are free.
  /// The caller should show a "preparing" state around the first one.
  Future<bool> prepare(String language) async {
    if (_engine != null && _engineLanguage == language) {
      return _engine!.alive;
    }
    try {
      final files = await _models.ensureInstalled(language);
      if (files == null) return false;
      await _engine?.dispose();
      _engine = await _AsrIsolate.spawn(files, language);
      _engineLanguage = language;
      return _engine!.alive;
    } on Object catch (e) {
      debugPrint('transcriber prepare failed: $e');
      _engine = null;
      _engineLanguage = null;
      return false;
    }
  }

  /// Start listening. Prompts for the microphone the first time. Returns
  /// whether recording actually began — false means no permission, no model, or
  /// no engine, and the caller should leave the screen on touch. Call [stop] to
  /// end and get the transcript.
  Future<bool> start(String language) async {
    try {
      if (!await prepare(language)) return false;
      // `hasPermission` asks the OS if the answer is not yet determined.
      if (!await _recorder.hasPermission()) return false;
      _pcm.clear();
      final stream = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: _sampleRate,
          numChannels: 1,
        ),
      );
      _sub = stream.listen((chunk) => _pcm.addAll(chunk));
      return true;
    } on Object catch (e) {
      debugPrint('transcriber start failed: $e');
      return false;
    }
  }

  /// Stop listening and decode. Returns '' on any failure or if nothing was
  /// captured. The buffered audio is cleared before this returns; decoding
  /// happens in the isolate, so the UI stays responsive with a spinner.
  Future<String> stop() async {
    try {
      await _sub?.cancel();
      _sub = null;
      await _recorder.stop();
      final engine = _engine;
      if (engine == null || !engine.alive || _pcm.isEmpty) {
        _pcm.clear();
        return '';
      }
      final samples = _toFloat32(_pcm);
      _pcm.clear();
      return (await engine.transcribe(samples, _sampleRate)).trim();
    } on Object catch (e) {
      debugPrint('transcriber stop failed: $e');
      _pcm.clear();
      return '';
    }
  }

  Float32List _toFloat32(List<int> bytes) {
    final byteData = Uint8List.fromList(bytes).buffer.asByteData();
    final count = bytes.length ~/ 2;
    final out = Float32List(count);
    for (var i = 0; i < count; i++) {
      out[i] = byteData.getInt16(i * 2, Endian.little) / 32768.0;
    }
    return out;
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    await _recorder.dispose();
    await _engine?.dispose();
    _engine = null;
  }
}

// ---------------------------------------------------------------------------
// The recogniser isolate.
// ---------------------------------------------------------------------------

/// Handle to a long-lived isolate that owns one `OfflineRecognizer`.
class _AsrIsolate {
  _AsrIsolate._(this._isolate, this._send, this._responses);

  final Isolate _isolate;
  final SendPort _send;
  final Stream<Object?> _responses;
  bool alive = true;

  static Future<_AsrIsolate> spawn(ModelFiles files, String language) async {
    final rx = ReceivePort();
    final isolate = await Isolate.spawn(
      _asrWorkerEntry,
      _AsrInit(rx.sendPort, files.encoder, files.decoder, files.tokens, language),
      errorsAreFatal: true,
      debugName: 'asr-$language',
    );
    final responses = rx.asBroadcastStream();
    // The worker's first message is its own SendPort once the recogniser is up.
    final first = await responses.first;
    if (first is! SendPort) {
      isolate.kill(priority: Isolate.immediate);
      throw StateError('asr isolate failed to initialise: $first');
    }
    return _AsrIsolate._(isolate, first, responses);
  }

  Future<String> transcribe(Float32List samples, int sampleRate) async {
    if (!alive) return '';
    _send.send(_AsrJob(samples, sampleRate));
    final reply = await _responses.first;
    if (reply is String) return reply;
    debugPrint('asr isolate error: $reply');
    return '';
  }

  Future<void> dispose() async {
    alive = false;
    _isolate.kill(priority: Isolate.immediate);
  }
}

class _AsrInit {
  const _AsrInit(
      this.reply, this.encoder, this.decoder, this.tokens, this.language);
  final SendPort reply;
  final String encoder;
  final String decoder;
  final String tokens;
  final String language;
}

class _AsrJob {
  const _AsrJob(this.samples, this.sampleRate);
  final Float32List samples;
  final int sampleRate;
}

/// Isolate entrypoint: build the recogniser once, then answer jobs forever.
void _asrWorkerEntry(_AsrInit init) {
  sherpa.OfflineRecognizer recognizer;
  try {
    sherpa.initBindings();
    recognizer = sherpa.OfflineRecognizer(
      sherpa.OfflineRecognizerConfig(
        model: sherpa.OfflineModelConfig(
          whisper: sherpa.OfflineWhisperModelConfig(
            encoder: init.encoder,
            decoder: init.decoder,
            // Whisper is multilingual; the interview language is fixed here for
            // the life of this isolate rather than auto-detected per clip.
            language: init.language,
            task: 'transcribe',
          ),
          tokens: init.tokens,
          modelType: 'whisper',
          // 2 big cores + 2 little on the target class of device. More than
          // this contends with the UI isolate for no gain.
          numThreads: 4,
        ),
      ),
    );
  } on Object catch (e) {
    init.reply.send('init failed: $e');
    return;
  }

  final rx = ReceivePort();
  init.reply.send(rx.sendPort);
  rx.listen((message) {
    if (message is! _AsrJob) return;
    try {
      final stream = recognizer.createStream();
      stream.acceptWaveform(
          samples: message.samples, sampleRate: message.sampleRate);
      recognizer.decode(stream);
      final text = recognizer.getResult(stream).text;
      stream.free();
      init.reply.send(text);
    } on Object catch (e) {
      init.reply.send('decode failed: $e');
    }
  });
}
