/// There is no voice capture in this app — 2/3 §1 rule 1, §15 item 11, §16.
///
/// This is the project's privacy claim, and it is load-bearing: *at the kiosk
/// the patient's voice never leaves the device*. A second, weaker voice path in
/// the phone app — where audio would go to a cloud recogniser — would qualify
/// that claim into meaninglessness.
///
/// So the absence is asserted rather than assumed. A dependency can add a
/// permission to a merged Android manifest without anyone editing a file in
/// this repository, and nobody would notice until a Play Store listing said
/// "this app can record audio".
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('no microphone anywhere', () {
    test('the Android manifest declares no audio permission', () {
      final manifests = [
        File('android/app/src/main/AndroidManifest.xml'),
        File('android/app/src/debug/AndroidManifest.xml'),
        File('android/app/src/profile/AndroidManifest.xml'),
      ].where((f) => f.existsSync());

      expect(manifests, isNotEmpty, reason: 'no Android manifest found to check');

      // Declarations, not mentions. A substring search over the whole file
      // cannot tell `<uses-permission android:name="...RECORD_AUDIO"/>` from a
      // comment saying there is deliberately no such permission — and the
      // comment explaining *why* a rule exists is worth more than the two
      // characters saved by matching loosely.
      final declaration = RegExp(
        r'<uses-permission[^>]*android:name\s*=\s*"([^"]+)"',
        multiLine: true,
      );

      for (final manifest in manifests) {
        final xml = manifest.readAsStringSync();
        final declared = declaration
            .allMatches(xml)
            .map((m) => m.group(1)!.split('.').last)
            .toSet();
        for (final permission in [
          'RECORD_AUDIO',
          'CAPTURE_AUDIO_OUTPUT',
          'MODIFY_AUDIO_SETTINGS',
        ]) {
          expect(declared, isNot(contains(permission)),
              reason: '${manifest.path} declares $permission');
        }
      }
    });

    test('the iOS Info.plist declares no microphone usage', () {
      final plist = File('ios/Runner/Info.plist');
      if (!plist.existsSync()) return;
      final xml = plist.readAsStringSync();
      expect(xml.contains('NSMicrophoneUsageDescription'), isFalse);
      expect(xml.contains('NSSpeechRecognitionUsageDescription'), isFalse);
    });

    test('no speech-recognition package is a dependency', () {
      // The check that catches it at the source rather than at the manifest.
      // `flutter_tts` is present and allowed — it is text-to-*speech*, output
      // only, and §11 explicitly warrants it for reading consent aloud.
      final pubspec = File('pubspec.yaml').readAsStringSync();
      for (final forbidden in [
        'speech_to_text',
        'speech_recognition',
        'record:',
        'flutter_sound',
        'mic_stream',
        'audio_recorder',
        'permission_handler',
      ]) {
        expect(pubspec.contains(forbidden), isFalse,
            reason: 'pubspec.yaml depends on $forbidden');
      }
      expect(pubspec.contains('flutter_tts'), isTrue,
          reason: 'consent read-aloud is output, and is meant to be here');
    });

    test('no source file references a speech recogniser', () {
      final offenders = <String>[];
      for (final entity in Directory('lib').listSync(recursive: true)) {
        if (entity is! File || !entity.path.endsWith('.dart')) continue;
        final source = entity.readAsStringSync();
        for (final needle in ['SpeechToText', 'startListening', 'AudioRecorder']) {
          if (source.contains(needle)) offenders.add('${entity.path}: $needle');
        }
      }
      expect(offenders, isEmpty);
    });
  });
}
