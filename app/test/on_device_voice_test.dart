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
        'assets/asr/indic-hi/model.int8.onnx',
        'assets/asr/indic-hi/tokens.txt',
      ]) {
        expect(File(f).existsSync(), isTrue,
            reason: '$f is missing from the repo. The .onnx files are Git LFS '
                'objects — a clone without `git lfs pull` leaves a pointer '
                'file here, and the APK then ships a microphone backed by '
                'nothing. Hindi is rebuildable with '
                'tool/asr/build_indicconformer.py.');
      }

      // An LFS pointer is a few hundred bytes of text. It satisfies
      // `existsSync` and fails at model load, on a device, mid-interview.
      for (final f in [
        'assets/asr/whisper-tiny/tiny-decoder.int8.onnx',
        'assets/asr/indic-hi/model.int8.onnx',
      ]) {
        expect(File(f).lengthSync(), greaterThan(1 << 20),
            reason: '$f looks like an unfetched Git LFS pointer, not a model');
      }
    });
  });

  group('voice is offered only where the model earns it', () {
    // A language gets a microphone when a bundled checkpoint has been measured
    // on it, and not before. Whisper-tiny romanises Hindi — on clean
    // synthesised speech "तीन दिनों से" came back as "Team denose", which is
    // not a rougher transcript but a different sentence, in a record a
    // physician acts on (DECISIONS §69). IndicConformer, converted for
    // sherpa-onnx, scores 0.04 CER on the same clips and reopened Hindi
    // (DECISIONS §76). The other seven languages are still unmeasured, so the
    // mic is still absent there and the patient taps or types.
    final models = File('lib/voice/asr_models.dart').readAsStringSync();

    /// The language keys of `AsrModel.registry`, read from the source so the
    /// policy stays one map in one file.
    Set<String> registeredLanguages() {
      final body = RegExp(r'registry\s*=\s*\{([^}]*)\}').firstMatch(models);
      expect(body, isNotNull,
          reason: 'the language -> model map must stay declared in one place');
      return RegExp(r"'([a-z]{2})'\s*:")
          .allMatches(body!.group(1)!)
          .map((m) => m.group(1)!)
          .toSet();
    }

    test('every served language names a model that is actually bundled', () {
      final pubspec = File('pubspec.yaml').readAsStringSync();
      expect(registeredLanguages(), containsAll(<String>{'en', 'hi'}));

      // Each registry entry's assetDir must be a declared, populated asset
      // directory. A language served by a checkpoint that is not in the APK is
      // a microphone that appears and then fails at first tap.
      final dirs = RegExp(r"assetDir:\s*'([^']+)'")
          .allMatches(models)
          .map((m) => m.group(1)!)
          .toSet();
      expect(dirs, isNotEmpty);
      for (final dir in dirs) {
        expect(pubspec.contains('$dir/'), isTrue,
            reason: '$dir is used by a model but not declared in pubspec.yaml');
        expect(Directory(dir).existsSync(), isTrue,
            reason: '$dir is declared but not present in the repo');
      }
    });

    test('an unmeasured language is offered no microphone at all', () {
      // The gate is in the model lookup, so every caller above it — isReady,
      // ensureModel, prepare — reports "not available" without a special case,
      // and ListenButton renders the absent microphone it already had.
      expect(models.contains('AsrModel? _modelFor'), isTrue,
          reason: 'the lookup must be able to answer "nothing serves this"');
      expect(models.contains('AsrModel.registry[language]'), isTrue);

      for (final unserved in ['bn', 'ta', 'te', 'mr', 'gu', 'kn', 'pa']) {
        expect(registeredLanguages().contains(unserved), isFalse,
            reason: 'no bundled model has been measured on $unserved; adding '
                'it here without a checkpoint that was ships romanised or '
                'mis-scripted answers into a clinical record. '
                'tool/asr/bench_hindi.py is how the measuring is done.');
      }
    });

    test('each engine a model declares is one the isolate can build', () {
      // asr_models.dart and transcribe.dart have to agree: a sealed ModelFiles
      // whose new subtype nobody handled is a compile error, and this keeps
      // the two halves of that pairing from drifting apart silently.
      final transcribe = File('lib/voice/transcribe.dart').readAsStringSync();
      expect(transcribe.contains('WhisperFiles()'), isTrue);
      expect(transcribe.contains('NemoCtcFiles()'), isTrue);
      expect(transcribe.contains('OfflineNemoEncDecCtcModelConfig'), isTrue,
          reason: 'a NeMo CTC checkpoint cannot be loaded through the Whisper '
              'config; handing it to the wrong one fails at model load');
    });
  });

  test('read-aloud is still output-only', () {
    // TTS gained no input path when STT arrived.
    final src = File('lib/voice/read_aloud.dart').readAsStringSync();
    expect(src.contains('startStream'), isFalse);
    expect(src.contains('AudioRecorder'), isFalse);
  });
}
