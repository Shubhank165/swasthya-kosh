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

  group('matchNumber', () {
    test('digits, number words and a mix all reach the same reading', () {
      for (final said in ['101', 'one oh one', 'a hundred and one']) {
        final m = matchNumber(
            transcript: said, language: 'en', minimum: 30, maximum: 110);
        expect(m.number, 101, reason: said);
      }
    });

    test('a decimal survives the transcript', () {
      expect(
          matchNumber(transcript: '38.5', language: 'en', minimum: 30, maximum: 45)
              .number,
          38.5);
      expect(
          matchNumber(
                  transcript: 'thirty eight point five',
                  language: 'en',
                  minimum: 30,
                  maximum: 45)
              .number,
          38.5);
    });

    test('tens and units are added, not concatenated', () {
      expect(matchNumber(transcript: 'twenty five', language: 'en').number, 25);
      expect(matchNumber(transcript: 'ninety nine', language: 'en').number, 99);
    });

    test('a reading outside the content bounds is not a match', () {
      // An impossible vital sign is worse than asking again.
      final m = matchNumber(
          transcript: 'one', language: 'en', minimum: 30, maximum: 110);
      expect(m.intent, SpokenIntent.none);
    });

    test('a stray number before the real one is skipped, not taken', () {
      final m = matchNumber(
          transcript: 'for 2 days it was one oh one',
          language: 'en',
          minimum: 30,
          maximum: 110);
      expect(m.number, 101);
    });

    test('a spoken unit selects it, and silence about units leaves it alone', () {
      final withUnit = matchNumber(
        transcript: 'a hundred and one fahrenheit',
        language: 'en',
        minimum: 30,
        maximum: 110,
        units: const ['celsius', 'fahrenheit'],
      );
      expect(withUnit.unit, 'fahrenheit');
      final bare = matchNumber(
        transcript: 'a hundred and one',
        language: 'en',
        minimum: 30,
        maximum: 110,
        units: const ['celsius', 'fahrenheit'],
      );
      expect(bare.number, 101);
      expect(bare.unit, isNull);
    });

    test('"centigrade" is celsius', () {
      expect(
          matchNumber(
            transcript: 'thirty eight point five centigrade',
            language: 'en',
            units: const ['celsius', 'fahrenheit'],
          ).unit,
          'celsius');
    });

    test('"don\'t know" is honoured', () {
      expect(matchNumber(transcript: 'no idea', language: 'en').intent,
          SpokenIntent.dontKnow);
    });
  });

  group('matchDuration', () {
    test('a number and a unit together', () {
      final m = matchDuration(transcript: 'three days', language: 'en');
      expect(m.number, 3);
      expect(m.unit, 'day');
      expect(matchDuration(transcript: '2 weeks', language: 'en').unit, 'week');
    });

    test('an article counts as one', () {
      final m = matchDuration(transcript: 'since a week', language: 'en');
      expect(m.number, 1);
      expect(m.unit, 'week');
    });

    test('a number with no unit is not a duration', () {
      // Three of what? Filling the figure and leaving whichever unit was
      // selected standing beside it would record a guess.
      expect(matchDuration(transcript: 'three', language: 'en').intent,
          SpokenIntent.none);
    });

    test('a unit with no number is not a duration either', () {
      expect(matchDuration(transcript: 'days', language: 'en').intent,
          SpokenIntent.none);
    });
  });

  group('a label spoken inside a sentence', () {
    test('a verbose answer still lands on its option', () {
      final m = matchOption(
        transcript: "it's a burning kind of pain, doctor",
        optionCodes: const ['burning', 'stabbing', 'dull'],
        labelFor: labels({
          'burning': 'Burning pain',
          'stabbing': 'Stabbing pain',
          'dull': 'Dull ache',
        }),
        language: 'en',
      );
      expect(m.optionCode, 'burning');
    });

    test('and an unrelated sentence still matches nothing', () {
      final m = matchOption(
        transcript: 'can you repeat the question please doctor',
        optionCodes: const ['burning', 'stabbing', 'dull'],
        labelFor: labels({
          'burning': 'Burning pain',
          'stabbing': 'Stabbing pain',
          'dull': 'Dull ache',
        }),
        language: 'en',
      );
      expect(m.intent, SpokenIntent.none);
    });

    test('a long sentence does not drift onto the wrong option', () {
      final m = matchOption(
        transcript: 'well it comes and goes through the day mostly in the evening',
        optionCodes: const ['burning', 'stabbing'],
        labelFor: labels({'burning': 'Burning pain', 'stabbing': 'Stabbing pain'}),
        language: 'en',
      );
      expect(m.intent, SpokenIntent.none);
    });
  });
}
