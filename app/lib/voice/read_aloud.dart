/// Read a question aloud, on the device — 2/3 §11, §14.
///
/// **Output only.** This is the same warrant `flutter_tts` already carries for
/// reading the consent notice, extended to every question so a patient who
/// cannot read the script they chose can still hear it. The platform TTS engine
/// runs on the device; nothing spoken leaves it. Voice *input* is handled
/// separately by `lib/voice/transcribe.dart` and is also fully on-device —
/// `test/on_device_voice_test.dart` holds both to that.
///
/// **It never falls back to another language.** A Tamil question read by an
/// en-US voice is a question the patient did not understand, played back as
/// though they had — the rule §16 applies to option labels, applied to audio.
/// When the device has no voice for the chosen language the control is simply
/// absent.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// App language code -> the BCP-47 tag the platform TTS engine expects.
///
/// Indian locales throughout: the voice a patient hears should be the one that
/// pronounces their language the way it is spoken here, not a diaspora accent.
const Map<String, String> ttsLocales = {
  'en': 'en-IN',
  'hi': 'hi-IN',
  'bn': 'bn-IN',
  'ta': 'ta-IN',
  'te': 'te-IN',
  'mr': 'mr-IN',
  'gu': 'gu-IN',
  'kn': 'kn-IN',
  'pa': 'pa-IN',
};

String ttsLocaleFor(String language) => ttsLocales[language] ?? language;

/// The one utterance a screen builds from a question: the prompt, then each
/// option, in the order they appear, separated so the engine pauses between
/// them. Empty when the question has no prompt in this language — the caller
/// then shows no read-aloud control, matching what the screen itself does.
String spokenTextForQuestion({
  required String? prompt,
  required List<String> optionLabels,
}) {
  // No prompt, nothing to read: options without the question they answer are
  // not worth speaking, and the screen already treats a missing prompt as a
  // broken invariant rather than something to present.
  if (prompt == null || prompt.trim().isEmpty) return '';
  final parts = <String>[
    prompt.trim(),
    for (final label in optionLabels)
      if (label.trim().isNotEmpty) label.trim(),
  ];
  return parts.join('. ');
}

/// One TTS engine for the app, driven by [ReadAloudButton].
///
/// [speakingKey] holds the key of the utterance currently playing, or null.
/// Keying by utterance rather than a bare bool lets several read-aloud buttons
/// share one engine and each know whether it is the one talking.
class ReadAloud {
  ReadAloud({FlutterTts? tts}) : _tts = tts ?? FlutterTts() {
    _ready = _configure();
  }

  final FlutterTts _tts;
  late final Future<void> _ready;

  final ValueNotifier<String?> speakingKey = ValueNotifier<String?>(null);

  Future<void> _configure() async {
    // Every call here can throw if the platform has no TTS engine (or none in a
    // widget test). A device that cannot speak is not an error — the button
    // simply never appears — so the whole feature fails soft.
    try {
      // `speak` completes when the utterance finishes rather than when it is
      // queued, so the button can flip back to "listen" on its own.
      await _tts.awaitSpeakCompletion(true);
      _tts.setCompletionHandler(() => speakingKey.value = null);
      _tts.setCancelHandler(() => speakingKey.value = null);
      _tts.setErrorHandler((_) => speakingKey.value = null);
    } on Object {
      _unavailable = true;
    }
  }

  bool _unavailable = false;

  /// Whether the device can speak [language] at all. A missing voice means the
  /// button is not shown — never that the text is read in some other language.
  Future<bool> canSpeak(String language) async {
    await _ready;
    if (_unavailable) return false;
    try {
      final available = await _tts.isLanguageAvailable(ttsLocaleFor(language));
      return available == true || available == 1;
    } on Object {
      return false;
    }
  }

  /// Start speaking [text] in [language], or stop if [key] is already playing.
  Future<void> toggle({
    required String key,
    required String text,
    required String language,
  }) async {
    await _ready;
    if (speakingKey.value == key) {
      await stop();
      return;
    }
    if (!await canSpeak(language)) return;
    try {
      await _tts.stop();
      await _tts.setLanguage(ttsLocaleFor(language));
      speakingKey.value = key;
      await _tts.speak(text);
    } on Object {
      // Fall through: the utterance did not play, so the button must not be
      // left stuck on "stop".
    }
    if (speakingKey.value == key) speakingKey.value = null;
  }

  Future<void> stop() async {
    try {
      await _tts.stop();
    } on Object {
      // Nothing was playing, or the engine is gone. Either way, clear the flag.
    }
    speakingKey.value = null;
  }

  void dispose() {
    _tts.stop();
    speakingKey.dispose();
  }
}

final readAloudProvider = Provider<ReadAloud>((ref) {
  final service = ReadAloud();
  ref.onDispose(service.dispose);
  return service;
});
