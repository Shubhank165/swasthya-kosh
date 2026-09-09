/// Mic -> text, entirely on the device — 2/3 §16.
///
/// `record` opens the microphone at 16 kHz and hands this class a stream of
/// PCM. `sherpa_onnx` turns the samples into text. **Neither writes the audio
/// anywhere and nothing sends it** — the bytes live in memory for the few
/// seconds a patient is speaking and are gone when [stop] returns. The only
/// network this feature touches is the one-time model download in
/// `asr_models.dart`.
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

  /// True when [language]'s model is on disk and the mic is permitted, so the
  /// button can show. Never prompts; [ensureModel] does the download. Fails
  /// soft: no recorder plugin (or none in a test) reads as "not ready".
  Future<bool> isReady(String language) async {
    try {
      if (!await _recorder.hasPermission()) return false;
      return await _models.installed(language) != null;
    } on Object {
      return false;
    }
  }

  /// Whether the mic permission is currently granted (asking if it must).
  Future<bool> requestPermission() async {
    try {
      return await _recorder.hasPermission();
    } on Object {
      return false;
    }
  }

  /// Download [language]'s model if it is missing. Returns whether it is now
  /// present. Safe to call repeatedly; a failure leaves nothing partial.
  Future<bool> ensureModel(
    String language, {
    void Function(double fraction)? onProgress,
  }) async {
    try {
      if (await _models.installed(language) != null) return true;
      return await _models.download(language, onProgress: onProgress) != null;
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

  /// Start listening. Call [stop] to end and get the transcript.
  Future<void> start(String language) async {
    try {
      await _loadRecognizer(language);
      if (_recognizer == null) return;
      if (!await _recorder.hasPermission()) return;
      _pcm.clear();
      final stream = await _recorder.startStream(
        const RecordConfig(
          encoder: AudioEncoder.pcm16bits,
          sampleRate: _sampleRate,
          numChannels: 1,
        ),
      );
      _sub = stream.listen((chunk) => _pcm.addAll(chunk));
    } on Object catch (e) {
      debugPrint('transcriber start failed: $e');
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
