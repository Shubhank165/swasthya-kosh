/// One recorded answer — 2/3 §1 rule 4, §4, §9.
///
/// The status vocabulary is binding and arrives from the backend's canonical
/// record model. **Nothing in this app may collapse two of these into one.**
/// "Nobody asked", "the patient could not answer", "the patient declined" and
/// "the question does not apply" are four different medico-legal positions, and
/// none of them is "no".
library;

enum FieldStatus {
  /// The question was put and an answer was bound.
  answered('answered'),

  /// The patient was asked and said they do not know.
  ///
  /// On the Jetson this also covers "asked twice, could not bind an answer".
  /// Touch removes that case — a tap *is* the bound value — so in this app it
  /// means exactly one thing: the patient chose "I don't know".
  unresolved('unresolved'),

  /// The question was never put: skipped, or never reached.
  notAsked('not_asked'),

  /// A precondition ruled it out (§4: recorded, never omitted).
  notApplicable('not_applicable'),

  /// The patient was asked and declined to answer.
  refused('refused');

  const FieldStatus(this.wire);
  final String wire;
}

/// The value bound to an answered field.
///
/// **Serialises to the kiosk contract's shape, which is bare values rather than
/// a tagged union.** The backend's `coerce()` reads a raw scalar, or a mapping
/// like `{"n": 3, "unit": "day"}` or `{"code": "..."}`, and infers the canonical
/// type from the shape plus the field's `unit` hint. Emitting `{"kind": "text",
/// ...}` here would produce a record the normalizer reads as a mapping with no
/// magnitude and no code — a `Text` of the whole object.
///
/// That is exactly the drift §9's shared-fixture test exists to catch, which is
/// why these are checked against `tests/fixtures/kiosk/0.1.json` rather than
/// against a copy of it.
sealed class AnswerValue {
  const AnswerValue();

  /// The `value` field of a kiosk field entry.
  Object? toJson();

  /// A tag for the **draft** shape only — see [Answer.toJson].
  ///
  /// It exists because [toJson] is deliberately lossy: a coded option and a
  /// free-text answer both serialise to a bare string, which is exactly what
  /// the backend's `coerce()` wants and exactly what a resume cannot invert.
  /// Guessing on the way back in — "it is a string, call it text" — would work
  /// today and rot the first time a shape gains meaning, so the draft carries
  /// the tag and the wire does not.
  String get kind;

  /// The `unit` hint that travels beside it, where the shape alone is not
  /// enough for the backend to tell a duration from a quantity.
  String? get unitHint => null;
}

class TextValue extends AnswerValue {
  const TextValue(this.text);
  final String text;
  @override
  Object? toJson() => text;
  @override
  String get kind => 'text';
}

class BoolValue extends AnswerValue {
  const BoolValue(this.value);
  final bool value;
  @override
  Object? toJson() => value;
  @override
  String get kind => 'bool';
}

class NumberValue extends AnswerValue {
  const NumberValue(this.value, {this.unit});
  final double value;
  final String? unit;
  @override
  Object? toJson() => value;
  @override
  String? get unitHint => unit;
  @override
  String get kind => 'number';
}

/// A 0-10 severity. Bare number with no unit: the backend reads an unhinted
/// number in that range as a `Scale`.
class ScaleValue extends AnswerValue {
  const ScaleValue(this.value);
  final double value;
  @override
  Object? toJson() => value;
  @override
  String get kind => 'scale';
}

class DurationValue extends AnswerValue {
  const DurationValue({required this.n, required this.unit});
  final double n;
  final String unit;
  @override
  Object? toJson() => {'n': n, 'unit': unit};
  @override
  String get kind => 'duration';
}

class DateValue extends AnswerValue {
  const DateValue(this.isoDate);
  final String isoDate;
  @override
  Object? toJson() => isoDate;
  @override
  String get kind => 'date';
}

/// A chosen option. Sent as the bare option string, which is how the kiosk
/// sends `"abdominal_pain"` — the backend's ontology maps it to a concept.
class CodedValue extends AnswerValue {
  const CodedValue(this.code);
  final String code;
  @override
  Object? toJson() => code;
  @override
  String get kind => 'coded';
}

/// A multi-choice answer. A list, which the backend renders as comma-joined
/// text — the same treatment the kiosk's multi-selects get.
class CodedListValue extends AnswerValue {
  const CodedListValue(this.codes);
  final List<String> codes;
  @override
  Object? toJson() => codes;
  @override
  String get kind => 'coded_list';
}

/// Rebuild a value from the draft shape.
///
/// Returns null for an unrecognised tag rather than throwing: a draft written
/// by a newer build of the app must not make this one unable to start, and a
/// value it cannot read becomes an unanswered question the patient is asked
/// again — which is the safe direction to fail in.
AnswerValue? answerValueFromDraft(String? kind, Object? json, {String? unit}) {
  if (json == null) return null;
  return switch (kind) {
    'text' => TextValue(json.toString()),
    'bool' => json is bool ? BoolValue(json) : null,
    'number' => json is num ? NumberValue(json.toDouble(), unit: unit) : null,
    'scale' => json is num ? ScaleValue(json.toDouble()) : null,
    'duration' => json is Map && json['n'] is num && json['unit'] is String
        ? DurationValue(n: (json['n'] as num).toDouble(), unit: json['unit'] as String)
        : null,
    'date' => DateValue(json.toString()),
    'coded' => CodedValue(json.toString()),
    'coded_list' =>
      json is List ? CodedListValue([for (final code in json) code.toString()]) : null,
    _ => null,
  };
}

/// What the walker records for one question.
class Answer {
  const Answer({
    required this.questionId,
    required this.fieldId,
    required this.status,
    this.value,
    this.originalText,
    this.askedText,
    this.language,
    this.notApplicableBecause,
  });

  final String questionId;
  final String fieldId;
  final FieldStatus status;
  final AnswerValue? value;

  /// What the patient chose, as shown to them. Travels with every fact so the
  /// physician can always see the patient's own words rather than only the
  /// normalised code (backend §4).
  final String? originalText;

  /// The prompt actually shown, in the language actually used (§9).
  final String? askedText;
  final String? language;

  /// Why a precondition ruled this out. Recorded rather than omitted, so
  /// "not applicable" is a statement rather than an absence.
  final String? notApplicableBecause;

  /// Read one entry back out of a saved draft — §5 resume, §15 item 7.
  ///
  /// The inverse of [toJson], and only of [toJson]. It never reads the wire
  /// shape: a record that has been submitted is the hospital's, and nothing in
  /// this app parses one back.
  factory Answer.fromDraftJson(Map<String, dynamic> json) => Answer(
        questionId: json['question_id'] as String,
        fieldId: json['field_id'] as String,
        status: FieldStatus.values.firstWhere(
          (s) => s.wire == json['status'],
          // An unreadable status is `not_asked`, never `answered`. Rule 4: the
          // app may lose certainty on the way back in, never gain it.
          orElse: () => FieldStatus.notAsked,
        ),
        value: answerValueFromDraft(
          json['value_kind'] as String?,
          json['value'],
          unit: json['unit'] as String?,
        ),
        originalText: json['original_text'] as String?,
        askedText: json['asked_text'] as String?,
        language: json['language'] as String?,
        notApplicableBecause: json['not_applicable_because'] as String?,
      );

  bool get isSettled => status == FieldStatus.answered;

  /// Whether the question was actually put to the patient.
  ///
  /// True for everything the patient acted on, including a skip and an "I don't
  /// know"; false for the statuses the walker wrote by itself while scanning
  /// ahead. [askedText] is the discriminator because it is set exactly when a
  /// prompt was rendered on a screen, and the distinction matters for going
  /// back: retracting a question must re-derive the walker's own conclusions
  /// and must not silently discard the patient's.
  bool get wasPut => askedText != null;

  Answer copyWith({FieldStatus? status, AnswerValue? value, String? originalText}) => Answer(
        questionId: questionId,
        fieldId: fieldId,
        status: status ?? this.status,
        value: value ?? this.value,
        originalText: originalText ?? this.originalText,
        askedText: askedText,
        language: language,
        notApplicableBecause: notApplicableBecause,
      );

  /// One entry of the record's `fields` map — 2/3 §9.
  ///
  /// `value` is present as an explicit null for every unsettled status rather
  /// than omitted: the contract keeps one shape, and a reader must never have
  /// to infer a status from a missing key.
  Map<String, dynamic> toFieldJson({int? sourceTurn}) => {
        'value': status == FieldStatus.answered ? value?.toJson() : null,
        'status': status.wire,
        if (value?.unitHint != null) 'unit': value!.unitHint,
        if (originalText != null) 'original_text': originalText,
        if (sourceTurn != null) 'source_turn': sourceTurn,
        if (notApplicableBecause != null)
          'not_applicable_because': notApplicableBecause,
      };

  /// The debug/draft shape. Not the wire format — see [toFieldJson].
  Map<String, dynamic> toJson() => {
        'question_id': questionId,
        'field_id': fieldId,
        'status': status.wire,
        'value': value?.toJson(),
        'value_kind': value?.kind,
        'unit': value?.unitHint,
        'original_text': originalText,
        'asked_text': askedText,
        'language': language,
        if (notApplicableBecause != null)
          'not_applicable_because': notApplicableBecause,
      };
}
