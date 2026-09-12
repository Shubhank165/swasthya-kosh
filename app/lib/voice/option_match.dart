/// Turn a spoken phrase into an answer — 2/3 §16.
///
/// **Two modes.** On a choice or yes/no question the phrase can only ever pick
/// from what is already on screen — the options, or yes / no / "I'm not sure" —
/// and anything that does not clearly land on one of those is *not an answer*:
/// it returns none, the screen stays put, and the patient says it again or
/// taps. A confident wrong match is the failure mode worth preventing, so the
/// threshold is deliberately not generous.
///
/// On a **descriptive** question there is nothing to match against: the words
/// *are* the answer. [matchDictation] hands them back verbatim for the text box,
/// where the patient reads and corrects them before Continue — the edit step is
/// what makes an imperfect transcript safe there.
///
/// Matching is on the label the option is *displayed with*, in the language the
/// patient chose — the same string §9 requires be recorded — never on the
/// English code.
library;

import 'dart:math' as math;

/// What a spoken phrase resolved to.
enum SpokenIntent { option, dontKnow, none }

class SpokenMatch {
  const SpokenMatch(
    this.intent, {
    this.optionCode,
    this.heardLabel,
    this.number,
    this.unit,
  });

  final SpokenIntent intent;

  /// The option's code, when [intent] is [SpokenIntent.option].
  final String? optionCode;

  /// The label that was matched, for recording as the patient's own words.
  final String? heardLabel;

  /// The quantity heard, for a number or duration question. Null everywhere
  /// else — a choice question has no number to report.
  final double? number;

  /// The unit heard alongside [number], when the patient said one. Null means
  /// they gave a bare figure and the widget's current unit stands: a patient
  /// who says "hundred and one" on a screen already set to Fahrenheit has not
  /// changed their mind about the scale.
  final String? unit;

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

/// 0..1 similarity between what was said and an option label.
///
/// [a] is the transcript and [b] the label, and the asymmetry matters: a
/// patient answers in a sentence and the label is two or three words inside it.
/// Scoring the whole utterance against the label punishes them for speaking
/// naturally — "it's a burning kind of pain, doctor" shares two tokens out of a
/// union of seven with "burning pain", 0.29, under the floor — so the label is
/// scored against the best matching *window* of the transcript instead.
///
/// The floor is unchanged. A weak scorer is fixed by fixing the scorer; lowering
/// the bar instead would buy the same recall by accepting wrong matches, and a
/// confident wrong match is the failure mode this module exists to prevent.
double _similarity(String a, String b) {
  final tokens = _normalise(a).split(' ').where((t) => t.isNotEmpty).toList();
  final width = _normalise(b).split(' ').where((t) => t.isNotEmpty).length;
  if (tokens.length <= width + 1) return _windowScore(a, b);

  var best = _windowScore(a, b);
  // n-1, n and n+1 tokens: a label of n words is said in about n words, give or
  // take an article. Wider than that and the window is the sentence again.
  for (var size = math.max(1, width - 1); size <= width + 1; size++) {
    for (var start = 0; start + size <= tokens.length; start++) {
      final window = tokens.sublist(start, start + size).join(' ');
      final score = _windowScore(window, b);
      if (score > best) best = score;
      if (best == 1) return 1;
    }
  }
  return best;
}

/// Token overlap, with a Levenshtein-ratio fallback for a one-word answer heard
/// slightly wrong.
double _windowScore(String a, String b) {
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

/// A descriptive question takes the words as spoken. There is nothing to match
/// against — the transcript is handed back as [SpokenMatch.heardLabel] for the
/// text box, and the patient corrects it before it is recorded. "I don't know"
/// is still honoured so a question can be dismissed by voice.
SpokenMatch matchDictation({
  required String transcript,
  required String language,
}) {
  final text = transcript.trim();
  if (text.isEmpty) return SpokenMatch.none;
  if (_containsPhrase(transcript, _dontKnowPhrases[language] ?? const [])) {
    return const SpokenMatch(SpokenIntent.dontKnow);
  }
  return SpokenMatch(SpokenIntent.option, heardLabel: text);
}

// --- numbers -----------------------------------------------------------------

/// English number words. **English only, and that is not a gap.**
///
/// The mic is offered only in languages the on-device model can actually write
/// (`asr_models.dart`, `DECISIONS.md §69`), and today that is English alone. A
/// Hindi word list here would parse transcripts that never arrive, and would
/// have to be rewritten the day a model that does write Devanagari lands — at
/// which point the words it emits are a thing to measure, not to guess.
const Map<String, int> _numberWords = {
  'zero': 0, 'oh': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
  'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
  'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
  'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30,
  'forty': 40, 'fourty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70,
  'eighty': 80, 'ninety': 90,
};

/// Kept as a separate normaliser from [_normalise] because that one strips the
/// decimal point, and "38.5" arriving as "38 5" is two numbers, neither right.
String _normaliseNumeric(String s) => s
    .toLowerCase()
    .replaceAll(RegExp(r'(?<=\d),(?=\d)'), '')
    .replaceAll(RegExp(r'[^\p{L}\p{N}\s.]', unicode: true), ' ')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();

/// Every quantity in [transcript], in the order spoken.
///
/// Digits and words both, because a transcript mixes them freely — "101.4",
/// "one oh one point four" and "a hundred and one" are the same reading said
/// three ways.
List<double> _numbersIn(String transcript) {
  final tokens = _normaliseNumeric(transcript).split(' ');
  final found = <double>[];

  var accumulator = 0.0; // completed hundreds
  var current = 0.0; // the part being built
  var started = false;
  var decimals = <int>[];
  var inDecimal = false;
  int? previous; // the last word value, to tell "twenty five" from "one oh one"

  void flush() {
    previous = null;
    if (!started) return;
    var value = accumulator + current;
    if (decimals.isNotEmpty) {
      value += double.parse('0.${decimals.join()}');
    }
    found.add(value);
    accumulator = 0;
    current = 0;
    started = false;
    inDecimal = false;
    decimals = <int>[];
  }

  for (final token in tokens) {
    if (token.isEmpty) continue;

    final digits = double.tryParse(token);
    if (digits != null) {
      // A bare figure ends whatever was being spelled out and stands alone.
      flush();
      found.add(digits);
      continue;
    }

    if (token == 'and' && started) continue; // "a hundred and one"
    if (token == 'a' || token == 'an') continue; // "a hundred", "a week"

    if (token == 'point' || token == 'decimal') {
      if (started) inDecimal = true;
      continue;
    }

    final word = _numberWords[token];
    if (word != null) {
      started = true;
      if (inDecimal) {
        // After "point", digits are read one at a time: "point four five".
        if (word < 10) decimals.add(word);
        continue;
      }
      if (current == 0) {
        current = word.toDouble();
      } else if (word >= 20) {
        // "five ninety" is two readings, not one.
        flush();
        started = true;
        current = word.toDouble();
      } else if (previous != null && previous! < 10) {
        // Digits read one at a time: "one oh one" is 101, not 11.
        current = current * 10 + word;
      } else if (current % 10 == 0 && current < 100) {
        current += word; // "twenty five"
      } else {
        flush();
        started = true;
        current = word.toDouble();
      }
      previous = word;
      continue;
    }

    if (token == 'hundred') {
      started = true;
      accumulator += (current == 0 ? 1 : current) * 100;
      current = 0;
      previous = null;
      continue;
    }
    if (token == 'thousand') {
      started = true;
      accumulator = (accumulator + current == 0 ? 1 : accumulator + current) * 1000;
      current = 0;
      previous = null;
      continue;
    }

    // Any other word ends the run. "thirty eight degrees celsius" is one
    // number; the words after it are not part of it.
    flush();
  }
  flush();
  return found;
}

/// Unit words, per unit code the content may name. The code itself always
/// counts; these are the things a patient says instead.
const Map<String, List<String>> _unitWords = {
  'celsius': ['celsius', 'centigrade', 'degrees c', 'degree c'],
  'fahrenheit': ['fahrenheit', 'degrees f', 'degree f'],
  'kg': ['kg', 'kilo', 'kilos', 'kilogram', 'kilograms'],
  'cm': ['cm', 'centimetre', 'centimeter', 'centimetres', 'centimeters'],
  'hour': ['hour', 'hours', 'hrs', 'hr'],
  'day': ['day', 'days'],
  'week': ['week', 'weeks'],
  'month': ['month', 'months'],
  'year': ['year', 'years', 'yr', 'yrs'],
};

/// The unit named in [transcript], out of [units], or null when none is.
String? _unitIn(String transcript, List<String> units) {
  final tokens = _normalise(transcript).split(' ').toSet();
  final text = _normalise(transcript);
  for (final unit in units) {
    final words = [unit, ...(_unitWords[unit] ?? const [])];
    for (final word in words) {
      final needle = _normalise(word);
      if (needle.isEmpty) continue;
      // A single word must be a whole token — "c" must not match "because".
      final hit = needle.contains(' ') ? text.contains(needle) : tokens.contains(needle);
      if (hit) return unit;
    }
  }
  return null;
}

/// Resolve [transcript] for a numeric question.
///
/// Returns none rather than a reading outside [minimum]..[maximum]. A
/// temperature question bounded at 30–110 °F that heard "one" has misheard
/// something; recording 1 °F as a vital sign would be worse than asking again.
/// Where the content gives no bounds, any number is accepted — the patient
/// confirms it on screen before it is recorded either way.
SpokenMatch matchNumber({
  required String transcript,
  required String language,
  double? minimum,
  double? maximum,
  List<String> units = const [],
}) {
  if (_containsPhrase(transcript, _dontKnowPhrases[language] ?? const [])) {
    return const SpokenMatch(SpokenIntent.dontKnow);
  }
  final unit = _unitIn(transcript, units);
  for (final candidate in _numbersIn(transcript)) {
    if (minimum != null && candidate < minimum) continue;
    if (maximum != null && candidate > maximum) continue;
    return SpokenMatch(
      SpokenIntent.option,
      number: candidate,
      unit: unit,
      heardLabel: transcript.trim(),
    );
  }
  return SpokenMatch.none;
}

/// Resolve [transcript] for a duration question — "three days", "2 weeks".
///
/// Both halves are required. A bare "three" does not say three of what, and
/// defaulting the unit would put a guess on the record.
SpokenMatch matchDuration({
  required String transcript,
  required String language,
  List<String> units = const ['hour', 'day', 'week', 'month', 'year'],
}) {
  if (_containsPhrase(transcript, _dontKnowPhrases[language] ?? const [])) {
    return const SpokenMatch(SpokenIntent.dontKnow);
  }
  final unit = _unitIn(transcript, units);
  if (unit == null) return SpokenMatch.none;
  final numbers = _numbersIn(transcript);
  // "since a week" / "for a day" — the article is the quantity.
  final n = numbers.isNotEmpty
      ? numbers.first
      : (RegExp(r'\b(a|an|one)\b').hasMatch(_normalise(transcript)) ? 1.0 : null);
  if (n == null || n <= 0) return SpokenMatch.none;
  return SpokenMatch(
    SpokenIntent.option,
    number: n,
    unit: unit,
    heardLabel: transcript.trim(),
  );
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
