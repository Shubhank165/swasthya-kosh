/// Mic -> text, entirely on the device — 2/3 §16.
///
/// `record` opens the microphone at 16 kHz and hands this class a stream of
/// PCM. `sherpa_onnx` turns the samples into text. **Neither writes the audio
/// anywhere and nothing sends it** — the bytes live in memory for the few
/// seconds a patient is speaking and are gone when [stop] returns. The model
/// ships in the APK, so this feature touches no network at all.
///
/// Like the backend's Gemini adapter, this module is exercised by hand on a
/// device rather than in CI: it needs a real microphone and a real model, and
/// the unit tests cover the parts that do not — the matcher and the button's
/// guards. Every call here fails soft: no permission, no model, no engine, and
/// the caller gets an empty transcript and the patient uses touch.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';
import 'package:sherpa_onnx/sherpa_onnx.dart' as sherpa;

import 'asr_models.dart';

/// One [Transcriber] for the app — it holds an open recogniser and, briefly, a
/// mic stream, neither of which should be duplicated per screen.
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

  sherpa.OfflineRecognizer? _recognizer;
  String? _loadedFor;
  bool _bindingsReady = false;

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

  Future<void> _loadRecognizer(String language) async {
    if (_loadedFor == language && _recognizer != null) return;
    final files = await _models.installed(language);
    if (files == null) return;

    if (!_bindingsReady) {
      sherpa.initBindings();
      _bindingsReady = true;
    }
    _recognizer?.free();
    _recognizer = sherpa.OfflineRecognizer(
      sherpa.OfflineRecognizerConfig(
        model: sherpa.OfflineModelConfig(
          whisper: sherpa.OfflineWhisperModelConfig(
            encoder: files.encoder,
            decoder: files.decoder,
            // Whisper is multilingual; the interview language is set per call,
            // never baked into the file.
            language: language,
            task: 'transcribe',
          ),
          tokens: files.tokens,
          modelType: 'whisper',
          numThreads: 2,
        ),
      ),
    );
    _loadedFor = language;
  }

  /// Start listening. Prompts for the microphone the first time. Returns
  /// whether recording actually began — false means no permission or no engine,
  /// and the caller should leave the screen on touch. Call [stop] to end and
  /// get the transcript.
  Future<bool> start(String language) async {
    try {
      await _loadRecognizer(language);
      if (_recognizer == null) return false;
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
  /// captured. The buffered audio is cleared before this returns.
  Future<String> stop() async {
    try {
      await _sub?.cancel();
      _sub = null;
      await _recorder.stop();
      final recognizer = _recognizer;
      if (recognizer == null || _pcm.isEmpty) return '';

      final samples = _toFloat32(_pcm);
      _pcm.clear();

      final s = recognizer.createStream();
      s.acceptWaveform(samples: samples, sampleRate: _sampleRate);
      recognizer.decode(s);
      final text = recognizer.getResult(s).text.trim();
      s.free();
      return text;
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
    _recognizer?.free();
    _recognizer = null;
  }
}
