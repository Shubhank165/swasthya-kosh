/// Turn a spoken phrase into one of a question's options — 2/3 §16.
///
/// **This does not parse free text.** The offline bundle carries no free-text
/// interpreters (they run on the backend against the submitted record), so on
/// the phone a voice answer can only ever pick from what is already on screen:
/// the options of a choice question, or yes / no / "I'm not sure". Anything the
/// patient says that does not clearly land on one of those is *not an answer* —
/// it returns null, the screen stays put, and they are asked to say it again or
/// tap. A confident wrong match is the failure mode worth preventing, so the
/// threshold is deliberately not generous.
///
/// Matching is on the label the option is *displayed with*, in the language the
/// patient chose — the same string §9 requires be recorded — never on the
/// English code.
library;

import 'dart:math' as math;

/// What a spoken phrase resolved to.
enum SpokenIntent { option, dontKnow, none }

class SpokenMatch {
  const SpokenMatch(this.intent, {this.optionCode, this.heardLabel});

  final SpokenIntent intent;

  /// The option's code, when [intent] is [SpokenIntent.option].
  final String? optionCode;

  /// The label that was matched, for recording as the patient's own words.
  final String? heardLabel;

  static const none = SpokenMatch(SpokenIntent.none);
}

/// "I don't know" / "not sure" / "skip", per language. Kept short and literal —
/// a fuzzy match here would swallow real answers.
const Map<String, List<String>> _dontKnowPhrases = {
  'en': ['dont know', 'do not know', 'not sure', 'no idea', 'skip', 'cannot say'],
  'hi': ['pata nahi', 'nahi pata', 'maloom nahi', 'nahin pata', 'नहीं पता', 'पता नहीं', 'मालूम नहीं'],
  'bn': ['jani na', 'jani na', 'জানি না', 'বলতে পারছি না'],
  'ta': ['theriyathu', 'theriyaathu', 'தெரியாது', 'சொல்ல முடியாது'],
  'te': ['telidu', 'teliyadu', 'తెలియదు', 'చెప్పలేను'],
  'mr': ['mahit nahi', 'माहित नाही', 'सांगता येत नाही'],
  'gu': ['khabar nathi', 'ખબર નથી', 'કહી શકતો નથી'],
  'kn': ['gottilla', 'ಗೊತ್ತಿಲ್ಲ', 'ಹೇಳಲಾಗದು'],
  'pa': ['pata nahi', 'ਪਤਾ ਨਹੀਂ', 'ਦੱਸ ਨਹੀਂ ਸਕਦਾ'],
};

/// yes / no, per language — for a yes-no-unknown question. `true` = yes.
const Map<String, Map<bool, List<String>>> _yesNo = {
  'en': {true: ['yes', 'yeah', 'yep', 'correct', 'right'], false: ['no', 'nope', 'not']},
  'hi': {true: ['haan', 'ha', 'ji', 'ji haan', 'हाँ', 'हां', 'जी'], false: ['nahi', 'nahin', 'na', 'नहीं', 'ना']},
  'bn': {true: ['hyan', 'ha', 'হ্যাঁ', 'হ্যা'], false: ['na', 'না']},
  'ta': {true: ['aam', 'ama', 'aamaam', 'ஆம்', 'ஆமாம்'], false: ['illai', 'இல்லை']},
  'te': {true: ['avunu', 'ha', 'అవును'], false: ['kadu', 'ledu', 'కాదు', 'లేదు']},
  'mr': {true: ['ho', 'हो', 'होय'], false: ['nahi', 'नाही']},
  'gu': {true: ['ha', 'હા', 'હાં'], false: ['na', 'ના']},
  'kn': {true: ['houdu', 'ಹೌದು'], false: ['illa', 'ಇಲ್ಲ']},
  'pa': {true: ['haan', 'ha', 'ਹਾਂ', 'ਹਾ'], false: ['nahi', 'nahin', 'ਨਹੀਂ', 'ਨਾ']},
};

String _normalise(String s) => s
    .toLowerCase()
    .replaceAll(RegExp(r'[^\p{L}\p{N}\s]', unicode: true), ' ')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();

bool _containsPhrase(String haystack, List<String> phrases) {
  final h = _normalise(haystack);
  return phrases.any((phrase) {
    final needle = _normalise(phrase);
    return needle.isNotEmpty && (h == needle || h.contains(needle));
  });
}

/// 0..1 similarity: token overlap, with a Levenshtein-ratio fallback for a
/// one-word answer heard slightly wrong.
double _similarity(String a, String b) {
  final an = _normalise(a);
  final bn = _normalise(b);
  if (an.isEmpty || bn.isEmpty) return 0;
  if (an == bn) return 1;

  final at = an.split(' ').toSet();
  final bt = bn.split(' ').toSet();
  final overlap = at.intersection(bt).length;
  if (overlap > 0) {
    final union = at.union(bt).length;
    final jaccard = overlap / union;
    // A label fully contained in what was said ("burning" in "it is burning")
    // is a strong signal the token ratio alone understates.
    final contained = an.contains(bn) || bn.contains(an);
    return math.max(jaccard, contained ? 0.85 : 0);
  }

  final distance = _levenshtein(an, bn);
  return 1 - distance / math.max(an.length, bn.length);
}

int _levenshtein(String a, String b) {
  final rows = List<int>.generate(b.length + 1, (i) => i);
  for (var i = 1; i <= a.length; i++) {
    var prev = rows[0];
    rows[0] = i;
    for (var j = 1; j <= b.length; j++) {
      final tmp = rows[j];
      rows[j] = math.min(
        math.min(rows[j] + 1, rows[j - 1] + 1),
        prev + (a.codeUnitAt(i - 1) == b.codeUnitAt(j - 1) ? 0 : 1),
      );
      prev = tmp;
    }
  }
  return rows[b.length];
}

/// Below this, a spoken phrase is treated as "not caught" rather than forced
/// onto the nearest option.
const double kMatchFloor = 0.6;

/// Resolve [transcript] against a choice question's options.
///
/// [labelFor] returns the displayed label for an option code in the patient's
/// language, or null when the bundle carries none (an unlabelled option cannot
/// be matched by voice — the patient taps it).
SpokenMatch matchOption({
  required String transcript,
  required List<String> optionCodes,
  required String? Function(String code) labelFor,
  required String language,
}) {
  if (_containsPhrase(transcript, _dontKnowPhrases[language] ?? const [])) {
    return const SpokenMatch(SpokenIntent.dontKnow);
  }

  String? bestCode;
  String? bestLabel;
  var bestScore = 0.0;
  for (final code in optionCodes) {
    final label = labelFor(code);
    if (label == null || label.trim().isEmpty) continue;
    final score = _similarity(transcript, label);
    if (score > bestScore) {
      bestScore = score;
      bestCode = code;
      bestLabel = label;
    }
  }

  if (bestCode != null && bestScore >= kMatchFloor) {
    return SpokenMatch(SpokenIntent.option,
        optionCode: bestCode, heardLabel: bestLabel);
  }
  return SpokenMatch.none;
}

/// Resolve [transcript] for a yes / no / unknown question. Returns the option
/// code `'yes'`, `'no'`, or a [SpokenIntent.dontKnow] match, or none.
SpokenMatch matchYesNo({required String transcript, required String language}) {
  if (_containsPhrase(transcript, _dontKnowPhrases[language] ?? const [])) {
    return const SpokenMatch(SpokenIntent.dontKnow);
  }
  final table = _yesNo[language] ?? _yesNo['en']!;
  if (_containsPhrase(transcript, table[false] ?? const [])) {
    return const SpokenMatch(SpokenIntent.option, optionCode: 'no', heardLabel: 'no');
  }
  if (_containsPhrase(transcript, table[true] ?? const [])) {
    return const SpokenMatch(SpokenIntent.option, optionCode: 'yes', heardLabel: 'yes');
  }
  return SpokenMatch.none;
}
