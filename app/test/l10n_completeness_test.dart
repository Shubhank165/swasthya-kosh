/// Every language has every key — 2/3 §14, §15 item 13.
///
/// "A missing key fails the build." Flutter's own behaviour is to fall back to
/// the template locale, which for a patient-facing clinical app means a Tamil
/// speaker seeing an English button in the middle of a Tamil screen — most
/// dangerously on `answerDontKnow` and `answerSkip`, which record different
/// statuses and must be told apart.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:medikiosk_app/l10n/strings.dart';

void main() {
  final directory = Directory('lib/l10n');

  Map<String, dynamic> arb(String language) => jsonDecode(
        File('lib/l10n/app_$language.arb').readAsStringSync(),
      ) as Map<String, dynamic>;

  Set<String> keysOf(Map<String, dynamic> doc) =>
      doc.keys.where((k) => !k.startsWith('@')).toSet();

  test('all nine languages have an ARB file', () {
    final present = directory
        .listSync()
        .whereType<File>()
        .map((f) => f.uri.pathSegments.last)
        .where((n) => n.startsWith('app_') && n.endsWith('.arb'))
        .map((n) => n.substring(4, n.length - 4))
        .toSet();
    expect(present, uiLanguages.toSet());
  });

  test('every language has every key the template has', () {
    final template = keysOf(arb('en'));
    for (final language in uiLanguages) {
      final missing = template.difference(keysOf(arb(language)));
      expect(missing, isEmpty, reason: '$language is missing $missing');
    }
  });

  test('no language has a key the template does not', () {
    // An orphan key is a string nobody reads, usually left behind by a rename.
    final template = keysOf(arb('en'));
    for (final language in uiLanguages) {
      final extra = keysOf(arb(language)).difference(template);
      expect(extra, isEmpty, reason: '$language has orphan keys $extra');
    }
  });

  test('no value is left as its English original outside English', () {
    // Catches a key added to nine files by copy-paste and translated in one.
    // A handful of strings are legitimately identical across scripts — none
    // here are, so any match is an untranslated placeholder.
    final template = arb('en');
    for (final language in uiLanguages.where((l) => l != 'en')) {
      final doc = arb(language);
      final untranslated = keysOf(template)
          .where((key) => doc[key] == template[key])
          .toList();
      expect(untranslated, isEmpty,
          reason: '$language still has English for $untranslated');
    }
  });

  test('the generator reports nothing untranslated', () {
    // `l10n.yaml` writes this file on every `flutter gen-l10n`. Non-empty means
    // the generated class falls back to English somewhere.
    final report = File('l10n_untranslated.json');
    if (!report.existsSync()) return;
    final content = report.readAsStringSync().trim();
    expect(content.isEmpty || content == '{}', isTrue, reason: content);
  });

  test('placeholders survive every translation', () {
    // A dropped `{number}` in the urgent-care string means a patient is told to
    // call — and not told what.
    final template = arb('en');
    final placeholders = RegExp(r'\{(\w+)\}');
    for (final key in keysOf(template)) {
      final expected =
          placeholders.allMatches(template[key] as String).map((m) => m[1]).toSet();
      if (expected.isEmpty) continue;
      for (final language in uiLanguages) {
        final actual = placeholders
            .allMatches(arb(language)[key] as String)
            .map((m) => m[1])
            .toSet();
        expect(actual, expected, reason: '$key in $language');
      }
    }
  });

  test('the urgent-care wording names no condition, in any language', () {
    // §6: this screen tells the patient what to DO, never what they have.
    // Checked in English only for meaning; the other scripts are checked for
    // the Latin-script disease names a machine translation would leave behind.
    const forbidden = [
      'heart attack', 'stroke', 'infarction', 'meningitis', 'sepsis',
      'appendicitis', 'embolism', 'cancer', 'dengue',
    ];
    for (final language in uiLanguages) {
      final doc = arb(language);
      final text =
          '${doc['urgentTitle']} ${doc['urgentBody']} ${doc['urgentAction']}'
              .toLowerCase();
      for (final word in forbidden) {
        expect(text.contains(word), isFalse, reason: '$language mentions "$word"');
      }
    }
  });
}
