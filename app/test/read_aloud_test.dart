/// Read-aloud: the mapping, the utterance, and the button's language guard.
///
/// The engine itself is the platform's; what is worth testing here is that the
/// app never asks it to speak a language the device cannot, and never in a
/// language other than the one the patient chose.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/l10n/strings.dart';
import 'package:medikiosk_app/voice/read_aloud.dart';
import 'package:medikiosk_app/voice/read_aloud_button.dart';

class _FakeReadAloud implements ReadAloud {
  _FakeReadAloud({this.available = true});

  final bool available;
  final List<({String key, String text, String language})> spoken = [];

  @override
  final ValueNotifier<String?> speakingKey = ValueNotifier<String?>(null);

  @override
  Future<bool> canSpeak(String language) async => available;

  @override
  Future<void> speak({
    required String key,
    required String text,
    required String language,
  }) async {
    if (!available) return;
    spoken.add((key: key, text: text, language: language));
    speakingKey.value = key;
  }

  @override
  Future<void> toggle({
    required String key,
    required String text,
    required String language,
  }) async {
    if (speakingKey.value == key) {
      speakingKey.value = null;
      return;
    }
    await speak(key: key, text: text, language: language);
  }

  @override
  Future<void> stop() async => speakingKey.value = null;

  @override
  void dispose() => speakingKey.dispose();
}

Widget _host(Widget child, ReadAloud service) => ProviderScope(
      overrides: [readAloudProvider.overrideWithValue(service)],
      child: MaterialApp(
        localizationsDelegates: Strings.localizationsDelegates,
        supportedLocales: Strings.supportedLocales,
        home: Scaffold(body: child),
      ),
    );

void main() {
  group('ttsLocaleFor', () {
    test('every app language maps to an Indian locale', () {
      for (final code in ['en', 'hi', 'bn', 'ta', 'te', 'mr', 'gu', 'kn', 'pa']) {
        expect(ttsLocaleFor(code), endsWith('-IN'));
      }
    });

    test('an unknown code is passed through untouched, never guessed', () {
      expect(ttsLocaleFor('xx'), 'xx');
    });
  });

  group('spokenTextForQuestion', () {
    test('reads the prompt then each option, in order', () {
      final text = spokenTextForQuestion(
        prompt: 'How bad is the pain?',
        optionLabels: ['Mild', 'Moderate', 'Severe'],
      );
      expect(text, 'How bad is the pain?. Mild. Moderate. Severe');
    });

    test('is empty when there is no prompt — the button then shows nothing', () {
      expect(spokenTextForQuestion(prompt: null, optionLabels: ['a']), '');
      expect(spokenTextForQuestion(prompt: '   ', optionLabels: const []), '');
    });

    test('drops blank option labels rather than reading a pause for them', () {
      expect(
        spokenTextForQuestion(prompt: 'Q', optionLabels: ['', 'Yes', '  ']),
        'Q. Yes',
      );
    });
  });

  group('ReadAloudButton', () {
    testWidgets('is absent when the device has no voice for the language',
        (tester) async {
      final fake = _FakeReadAloud(available: false);
      await tester.pumpWidget(_host(
        const ReadAloudButton(
          utteranceKey: 'q1', text: 'Kaisa lag raha hai?', language: 'hi'),
        fake,
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('question.readAloud')), findsNothing);
      expect(fake.spoken, isEmpty);
    });

    testWidgets('reads the question on its own, in the chosen language',
        (tester) async {
      final fake = _FakeReadAloud();
      await tester.pumpWidget(_host(
        const ReadAloudButton(
          utteranceKey: 'q1', text: 'Kaisa lag raha hai?', language: 'hi'),
        fake,
      ));
      await tester.pumpAndSettle();

      // No tap: the question speaks the moment it appears.
      expect(fake.spoken.single.language, 'hi');
      expect(fake.spoken.single.text, 'Kaisa lag raha hai?');
      expect(find.byIcon(Icons.stop), findsOneWidget);
    });

    testWidgets('a new question reads itself once', (tester) async {
      final fake = _FakeReadAloud();
      await tester.pumpWidget(_host(
        const ReadAloudButton(
          utteranceKey: 'q1', text: 'First?', language: 'en'),
        fake,
      ));
      await tester.pumpAndSettle();
      await tester.pumpWidget(_host(
        const ReadAloudButton(
          utteranceKey: 'q2', text: 'Second?', language: 'en'),
        fake,
      ));
      await tester.pumpAndSettle();

      expect(fake.spoken.map((s) => s.text), ['First?', 'Second?']);
    });

    testWidgets('tapping while it speaks silences it', (tester) async {
      final fake = _FakeReadAloud();
      await tester.pumpWidget(_host(
        const ReadAloudButton(
          utteranceKey: 'q1', text: 'Kaisa lag raha hai?', language: 'hi'),
        fake,
      ));
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.stop), findsOneWidget);

      await tester.tap(find.byKey(const Key('question.readAloud')));
      await tester.pumpAndSettle();

      expect(fake.speakingKey.value, isNull);
      expect(find.byIcon(Icons.volume_off), findsOneWidget);
    });

    testWidgets('silencing one question never silences the next', (tester) async {
      // The mute used to be sticky — turning off read-aloud on one question
      // turned it off for every question after, until tapped back on. The
      // patient wants exactly the opposite: stopping this one must not touch
      // the next one's automatic read.
      final fake = _FakeReadAloud();
      await tester.pumpWidget(_host(
        const ReadAloudButton(
          utteranceKey: 'q1', text: 'First?', language: 'en'),
        fake,
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('question.readAloud')));
      await tester.pumpAndSettle();
      expect(fake.speakingKey.value, isNull);

      await tester.pumpWidget(_host(
        const ReadAloudButton(
          utteranceKey: 'q2', text: 'Second?', language: 'en'),
        fake,
      ));
      await tester.pumpAndSettle();

      expect(fake.spoken.map((s) => s.text), ['First?', 'Second?']);
      expect(find.byIcon(Icons.stop), findsOneWidget,
          reason: 'the new question is speaking on its own, unmuted');
    });

    testWidgets('tapping again while silent replays this question',
        (tester) async {
      final fake = _FakeReadAloud();
      await tester.pumpWidget(_host(
        const ReadAloudButton(
          utteranceKey: 'q1', text: 'Kaisa lag raha hai?', language: 'hi'),
        fake,
      ));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('question.readAloud')));
      await tester.pumpAndSettle();
      expect(find.byIcon(Icons.volume_off), findsOneWidget);

      await tester.tap(find.byKey(const Key('question.readAloud')));
      await tester.pumpAndSettle();

      expect(fake.spoken.map((s) => s.text),
          ['Kaisa lag raha hai?', 'Kaisa lag raha hai?']);
      expect(find.byIcon(Icons.stop), findsOneWidget);
    });

    testWidgets('renders nothing for an empty utterance', (tester) async {
      final fake = _FakeReadAloud();
      await tester.pumpWidget(_host(
        const ReadAloudButton(utteranceKey: 'q1', text: '', language: 'en'),
        fake,
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('question.readAloud')), findsNothing);
      expect(fake.spoken, isEmpty);
    });
  });
}
