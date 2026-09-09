/// The spoken-answer matcher — 2/3 §16.
///
/// The property that matters: a phrase that clearly names an option resolves to
/// it, and a phrase that does not resolves to *nothing* — never to the nearest
/// guess. A confident wrong match is worse than asking again.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/voice/option_match.dart';

void main() {
  // A small stand-in for the bundle's per-language option labels.
  String? Function(String) labels(Map<String, String> m) => (code) => m[code];

  group('matchOption', () {
    final digestion = {
      'comfortable': 'Comfortable',
      'burning': 'Burning',
      'heaviness': 'Heaviness',
      'nausea': 'Feeling sick',
    };

    test('an exact spoken label resolves to that option', () {
      final m = matchOption(
        transcript: 'burning',
        optionCodes: digestion.keys.toList(),
        labelFor: labels(digestion),
        language: 'en',
      );
      expect(m.intent, SpokenIntent.option);
      expect(m.optionCode, 'burning');
      expect(m.heardLabel, 'Burning');
    });

    test('a label spoken inside a sentence still resolves', () {
      final m = matchOption(
        transcript: 'it feels comfortable after eating',
        optionCodes: digestion.keys.toList(),
        labelFor: labels(digestion),
        language: 'en',
      );
      expect(m.optionCode, 'comfortable');
    });

    test('a near-miss on one word is tolerated', () {
      final m = matchOption(
        transcript: 'burnin',
        optionCodes: digestion.keys.toList(),
        labelFor: labels(digestion),
        language: 'en',
      );
      expect(m.optionCode, 'burning');
    });

    test('something unrelated resolves to nothing, not the nearest option', () {
      final m = matchOption(
        transcript: 'my head hurts a lot',
        optionCodes: digestion.keys.toList(),
        labelFor: labels(digestion),
        language: 'en',
      );
      expect(m.intent, SpokenIntent.none);
      expect(m.optionCode, isNull);
    });

    test('"I don\'t know" is its own intent, in the chosen language', () {
      final en = matchOption(
        transcript: 'I am not sure',
        optionCodes: digestion.keys.toList(),
        labelFor: labels(digestion),
        language: 'en',
      );
      expect(en.intent, SpokenIntent.dontKnow);

      final hi = matchOption(
        transcript: 'मुझे पता नहीं',
        optionCodes: const ['a', 'b'],
        labelFor: labels({'a': 'एक', 'b': 'दो'}),
        language: 'hi',
      );
      expect(hi.intent, SpokenIntent.dontKnow);
    });

    test('an unlabelled option cannot be matched by voice', () {
      final m = matchOption(
        transcript: 'anything',
        optionCodes: const ['x'],
        labelFor: (_) => null,
        language: 'en',
      );
      expect(m.intent, SpokenIntent.none);
    });

    test('matches a Hindi label spoken in Hindi', () {
      final m = matchOption(
        transcript: 'भारीपन',
        optionCodes: const ['comfortable', 'heaviness'],
        labelFor: labels({'comfortable': 'ठीक लगता है', 'heaviness': 'भारीपन'}),
        language: 'hi',
      );
      expect(m.optionCode, 'heaviness');
    });
  });

  group('matchYesNo', () {
    test('yes and no in several languages', () {
      expect(matchYesNo(transcript: 'yes', language: 'en').optionCode, 'yes');
      expect(matchYesNo(transcript: 'nope', language: 'en').optionCode, 'no');
      expect(matchYesNo(transcript: 'हाँ', language: 'hi').optionCode, 'yes');
      expect(matchYesNo(transcript: 'नहीं', language: 'hi').optionCode, 'no');
      expect(matchYesNo(transcript: 'இல்லை', language: 'ta').optionCode, 'no');
      expect(matchYesNo(transcript: 'ಹೌದು', language: 'kn').optionCode, 'yes');
    });

    test('an ambiguous phrase resolves to nothing', () {
      expect(matchYesNo(transcript: 'maybe later', language: 'en').intent,
          SpokenIntent.none);
    });

    test('"don\'t know" beats a stray yes/no token', () {
      expect(matchYesNo(transcript: 'I really do not know', language: 'en').intent,
          SpokenIntent.dontKnow);
    });
  });
}
