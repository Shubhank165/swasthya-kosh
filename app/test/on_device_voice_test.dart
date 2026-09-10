/// Voice stays on the device — 2/3 §16, and the DECISIONS entry that reversed
/// the touch-only stance.
///
/// The project's privacy claim used to be "there is no microphone." It is now
/// the stronger, and testable, "the microphone feeds an offline recogniser and
/// the audio never leaves the phone." This file is what stops that eroding: a
/// dependency that adds a cloud speech SDK, a stray `dio` call from the voice
/// code, or an audio buffer written to disk would all fail here rather than in
/// a Play Store data-safety disclosure.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  // Comments in pubspec.yaml name the forbidden packages to explain why they
  // are forbidden, so the check has to look at declarations, not prose.
  final pubspec = File('pubspec.yaml')
      .readAsLinesSync()
      .where((l) => !l.trimLeft().startsWith('#'))
      .join('\n');
  final voiceDir = Directory('lib/voice');

  Iterable<File> dartFiles(Directory dir) => dir
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart'));

  group('the microphone is for on-device recognition only', () {
    test('the Android manifest allows RECORD_AUDIO and nothing wider', () {
      final xml =
          File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
      final declared = RegExp(r'<uses-permission[^>]*android:name\s*=\s*"([^"]+)"')
          .allMatches(xml)
          .map((m) => m.group(1)!.split('.').last)
          .toSet();

      expect(declared, contains('RECORD_AUDIO'),
          reason: 'on-device voice input needs the mic permission');
      // Capturing another app's audio output, or changing the device's audio
      // routing, is not what this feature does and must not be requested.
      expect(declared, isNot(contains('CAPTURE_AUDIO_OUTPUT')));
      expect(declared, isNot(contains('MODIFY_AUDIO_SETTINGS')));
    });

    test('iOS asks for the mic with a reason and never for cloud dictation', () {
      final plist = File('ios/Runner/Info.plist');
      if (!plist.existsSync()) return;
      final xml = plist.readAsStringSync();
      if (xml.contains('NSMicrophoneUsageDescription')) {
        // A bare key with no string is a rejected App Store submission and an
        // unexplained prompt to the patient.
        expect(
          RegExp(r'NSMicrophoneUsageDescription</key>\s*<string>[^<]+</string>')
              .hasMatch(xml),
          isTrue,
          reason: 'the mic usage string must not be empty',
        );
      }
      // Apple's speech framework is server-backed. We do our own recognition.
      expect(xml.contains('NSSpeechRecognitionUsageDescription'), isFalse);
    });
  });

  group('the recogniser is offline', () {
    test('pubspec has the on-device stack and no cloud speech package', () {
      for (final onDevice in ['record:', 'sherpa_onnx:']) {
        expect(pubspec.contains(onDevice), isTrue,
            reason: 'pubspec.yaml should depend on $onDevice');
      }
      for (final cloud in [
        'speech_to_text',
        'speech_recognition',
        'google_speech',
        'google_ml_kit',
        'flutter_sound',
        'mic_stream',
        'assemblyai',
        'deepgram',
        // `record` exposes its own permission check; a second permission
        // library is a smell and was forbidden before voice existed.
        'permission_handler',
      ]) {
        expect(pubspec.contains(cloud), isFalse,
            reason: 'pubspec.yaml depends on $cloud');
      }
    });

    test('no source file reaches for a cloud recogniser', () {
      final offenders = <String>[];
      for (final file in dartFiles(Directory('lib'))) {
        final src = file.readAsStringSync();
        for (final needle in [
          'SpeechToText',
          'speech_to_text',
          'google_speech',
          'SFSpeechRecognizer',
          'RecognizerIntent',
        ]) {
          if (src.contains(needle)) offenders.add('${file.path}: $needle');
        }
      }
      expect(offenders, isEmpty);
    });

    test('transcription uses the offline API and keeps no audio', () {
      final src = File('lib/voice/transcribe.dart').readAsStringSync();
      expect(src.contains('OfflineRecognizer'), isTrue);
      // The PCM buffer is cleared, never persisted.
      expect(src.contains('_pcm.clear()'), isTrue);
      expect(RegExp(r'writeAsBytes|saveTo|\.wav').hasMatch(src), isFalse,
          reason: 'captured audio must never be written anywhere');
    });
  });

  group('the voice code never touches the network at all', () {
    test('lib/voice does not use the dio client or the API', () {
      final offenders = <String>[];
      for (final file in dartFiles(voiceDir)) {
        final src = file.readAsStringSync();
        for (final needle in [
          'package:dio',
          'ApiClient',
          'apiProvider',
          '/api/v1',
          '/intakes/',
        ]) {
          if (src.contains(needle)) offenders.add('${file.path}: $needle');
        }
      }
      expect(offenders, isEmpty);
    });

    test('nothing in lib/voice opens a socket, an HTTP client, or a URL', () {
      final offenders = <String>[];
      for (final file in dartFiles(voiceDir)) {
        final src = file.readAsStringSync();
        for (final needle in [
          'package:http',
          'HttpClient',
          'Socket',
          'WebSocket',
          'Uri.parse',
          'http://',
          'https://',
          '.get(',
          '.post(',
        ]) {
          if (src.contains(needle)) offenders.add('${file.path}: $needle');
        }
      }
      expect(offenders, isEmpty,
          reason: 'the ASR model ships in the APK — there is no download');
    });

    test('the model is a bundled asset, copied to storage, not fetched', () {
      final models = File('lib/voice/asr_models.dart').readAsStringSync();
      expect(models.contains('rootBundle') || models.contains('AssetBundle'),
          isTrue,
          reason: 'the model is loaded from the app bundle');
      expect(models.contains('getApplicationSupportDirectory'), isTrue,
          reason: "sherpa reads real paths, so assets are copied to the app's "
              'storage');

      final pubspec = File('pubspec.yaml').readAsStringSync();
      expect(pubspec.contains('assets/asr/'), isTrue,
          reason: 'the model must be declared as a bundled asset');
      for (final f in [
        'assets/asr/whisper-tiny/tiny-encoder.int8.onnx',
        'assets/asr/whisper-tiny/tiny-decoder.int8.onnx',
        'assets/asr/whisper-tiny/tiny-tokens.txt',
      ]) {
        expect(File(f).existsSync(), isTrue, reason: '$f is missing from the repo');
      }
    });
  });

  test('read-aloud is still output-only', () {
    // TTS gained no input path when STT arrived.
    final src = File('lib/voice/read_aloud.dart').readAsStringSync();
    expect(src.contains('startStream'), isFalse);
    expect(src.contains('AudioRecorder'), isFalse);
  });
}
