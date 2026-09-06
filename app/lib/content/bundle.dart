/// The question content bundle — 2/3 §3, §4.
///
/// This app is a renderer, not a brain. It downloads the same versioned content
/// the kiosk's Jetson walks and walks it; the clinical decisions about what to
/// ask, in what order, and what constitutes a red flag were made by a clinician
/// in `clinical/questions/**` and compiled by the backend.
///
/// These are plain immutable models over that wire format. Nothing here decides
/// anything — see `walker.dart` for the one place that does, and §16 for why
/// there must not be a second.
library;

import 'dart:convert';

/// A node of the expression language shared by preconditions and red-flag rules.
///
/// The nesting matters and is not decoration: the cardiac rule is
/// `chest pain AND sudden onset AND (breathless OR cold sweat)`, and flattening
/// it would require both symptoms on the criterion that exists to catch a heart
/// attack in a waiting room.
sealed class Condition {
  const Condition();

  factory Condition.fromJson(Map<String, dynamic> json) {
    if (json['all'] case final List<dynamic> nodes) {
      return AllOf(nodes.map((n) => Condition.fromJson(n as Map<String, dynamic>)).toList());
    }
    if (json['any'] case final List<dynamic> nodes) {
      return AnyOf(nodes.map((n) => Condition.fromJson(n as Map<String, dynamic>)).toList());
    }
    if (json['not'] case final Map<String, dynamic> node) {
      return NotNode(Condition.fromJson(node));
    }
    return Leaf(
      fieldId: json['field_id'] as String? ?? '',
      status: json['status'] as String?,
      oneOf: (json['in'] as List<dynamic>?)?.map((v) => v.toString()).toList(),
      equals: json['equals'],
      gte: (json['gte'] as num?)?.toDouble(),
      lte: (json['lte'] as num?)?.toDouble(),
    );
  }

  /// Every field this expression reads. Used to decide whether it can be
  /// evaluated yet.
  Set<String> get fieldsRead;
}

final class AllOf extends Condition {
  const AllOf(this.nodes);
  final List<Condition> nodes;
  @override
  Set<String> get fieldsRead => {for (final n in nodes) ...n.fieldsRead};
}

final class AnyOf extends Condition {
  const AnyOf(this.nodes);
  final List<Condition> nodes;
  @override
  Set<String> get fieldsRead => {for (final n in nodes) ...n.fieldsRead};
}

final class NotNode extends Condition {
  const NotNode(this.node);
  final Condition node;
  @override
  Set<String> get fieldsRead => node.fieldsRead;
}

final class Leaf extends Condition {
  const Leaf({
    required this.fieldId,
    this.status,
    this.oneOf,
    this.equals,
    this.gte,
    this.lte,
  });

  final String fieldId;
  final String? status;
  final List<String>? oneOf;
  final Object? equals;
  final double? gte;
  final double? lte;

  @override
  Set<String> get fieldsRead => {fieldId};
}

/// The answer shapes this app renders — §4 fixes the list.
///
/// [unknown] is not one of them: it is what an `answer_type` the app has never
/// heard of becomes, so a bundle from a newer content version degrades to a
/// skipped question rather than a crash.
enum AnswerType {
  singleChoice,
  multiChoice,
  yesNoUnknown,
  number,
  scale,
  duration,
  date,
  freeText,
  unknown;

  static AnswerType parse(String? raw) => switch (raw) {
        'single_choice' => AnswerType.singleChoice,
        'multi_choice' => AnswerType.multiChoice,
        'yes_no_unknown' => AnswerType.yesNoUnknown,
        'number' => AnswerType.number,
        'scale' => AnswerType.scale,
        'duration' => AnswerType.duration,
        'date' => AnswerType.date,
        'free_text' => AnswerType.freeText,
        _ => AnswerType.unknown,
      };
}

class Question {
  const Question({
    required this.questionId,
    required this.fieldId,
    required this.section,
    required this.answerType,
    required this.prompts,
    this.options,
    this.unit,
    this.units,
    this.minimum,
    this.maximum,
    this.required = true,
    this.allowSkip = true,
    this.allowUnknown = true,
    this.precondition,
  });

  factory Question.fromJson(Map<String, dynamic> json) => Question(
        questionId: json['question_id'] as String,
        fieldId: json['field_id'] as String,
        section: json['section'] as String? ?? 'hpi',
        answerType: AnswerType.parse(json['answer_type'] as String?),
        prompts: {
          for (final entry in (json['prompts'] as Map<String, dynamic>? ?? {}).entries)
            entry.key: entry.value.toString(),
        },
        options: (json['options'] as List<dynamic>?)?.map((v) => v.toString()).toList(),
        unit: json['unit'] as String?,
        units: (json['units'] as List<dynamic>?)?.map((v) => v.toString()).toList(),
        minimum: (json['min'] as num?)?.toDouble(),
        maximum: (json['max'] as num?)?.toDouble(),
        required: json['required'] as bool? ?? true,
        allowSkip: json['allow_skip'] as bool? ?? true,
        allowUnknown: json['allow_unknown'] as bool? ?? true,
        precondition: json['precondition'] == null
            ? null
            : Condition.fromJson(json['precondition'] as Map<String, dynamic>),
      );

  final String questionId;
  final String fieldId;
  final String section;
  final AnswerType answerType;

  /// Language code to prompt text. **There is no fallback to English here on
  /// purpose** — see [promptFor].
  final Map<String, String> prompts;
  final List<String>? options;
  final String? unit;

  /// Units the patient may answer in, with [unit] the default. Null or a single
  /// entry means no choice is offered.
  final List<String>? units;
  final double? minimum;
  final double? maximum;
  final bool required;
  final bool allowSkip;
  final bool allowUnknown;
  final Condition? precondition;

  /// The prompt in [language], or `null` when this bundle has none.
  ///
  /// A caller that gets `null` must not ask the question. Falling back to
  /// English would put an English clinical question in front of a patient who
  /// chose Tamil, and record their answer as though they had understood it —
  /// which is a false record, not a cosmetic problem. The backend refuses to
  /// advertise a language it has no prompts for, so this should be
  /// unreachable; it returns `null` rather than asserting because a wrong
  /// bundle must not crash a patient's phone.
  String? promptFor(String language) => prompts[language];
}

class RedFlagRule {
  const RedFlagRule({
    required this.ruleId,
    required this.severity,
    required this.criteria,
  });

  factory RedFlagRule.fromJson(Map<String, dynamic> json) => RedFlagRule(
        ruleId: json['rule_id'] as String,
        severity: json['severity'] as String? ?? 'high',
        criteria: Condition.fromJson(json['criteria'] as Map<String, dynamic>),
      );

  final String ruleId;
  final String severity;
  final Condition criteria;
}

class ContentBundle {
  const ContentBundle({
    required this.bundleFormat,
    required this.contentVersion,
    required this.schemaVersion,
    required this.languages,
    required this.sections,
    required this.core,
    required this.branches,
    required this.ayurveda,
    this.ayurvedaCurrentState = const [],
    required this.questions,
    required this.redFlagRules,
  });

  factory ContentBundle.fromJson(Map<String, dynamic> json) {
    final questions = <String, Question>{};
    for (final raw in (json['questions'] as List<dynamic>? ?? [])) {
      final question = Question.fromJson(raw as Map<String, dynamic>);
      questions[question.questionId] = question;
    }
    return ContentBundle(
      bundleFormat: json['bundle_format'] as String? ?? '0',
      contentVersion: json['content_version'] as String? ?? 'unknown',
      schemaVersion: json['schema_version'] as String? ?? 'unknown',
      languages: (json['languages'] as List<dynamic>? ?? []).map((v) => v.toString()).toList(),
      sections: (json['sections'] as List<dynamic>? ?? []).map((v) => v.toString()).toList(),
      core: (json['core'] as List<dynamic>? ?? []).map((v) => v.toString()).toList(),
      branches: {
        for (final entry in (json['branches'] as Map<String, dynamic>? ?? {}).entries)
          entry.key: (entry.value as List<dynamic>).map((v) => v.toString()).toList(),
      },
      ayurveda: (json['ayurveda'] as List<dynamic>? ?? []).map((v) => v.toString()).toList(),
      ayurvedaCurrentState: (json['ayurveda_current_state'] as List<dynamic>? ?? [])
          .map((v) => v.toString())
          .toList(),
      questions: questions,
      redFlagRules: (json['red_flag_rules'] as List<dynamic>? ?? [])
          .map((r) => RedFlagRule.fromJson(r as Map<String, dynamic>))
          .toList(),
    );
  }

  static ContentBundle parse(String source) =>
      ContentBundle.fromJson(jsonDecode(source) as Map<String, dynamic>);

  final String bundleFormat;
  final String contentVersion;
  final String schemaVersion;
  final List<String> languages;
  final List<String> sections;

  /// Question ids asked of every patient, in order.
  final List<String> core;

  /// Chief-complaint value to the question ids that complaint adds.
  final Map<String, List<String>> branches;
  final List<String> ayurveda;

  /// The Ayurveda questions a returning patient is asked again — §5 screen 8.
  ///
  /// Empty on a bundle from a backend that predates the field, which is why the
  /// walker treats empty as "ask the full set": a returning patient answering
  /// nine questions instead of three is slower, and a returning patient
  /// answering none of them loses Agni, Nidra and Koshtha for today.
  final List<String> ayurvedaCurrentState;
  final Map<String, Question> questions;
  final List<RedFlagRule> redFlagRules;

  /// The record schema versions this app can produce.
  ///
  /// §4: if the bundle names a schema this app cannot produce, refuse to start
  /// an intake and tell the user to update. **Do not attempt partial
  /// compatibility** — a record that is half of a newer contract is a record
  /// the backend will either reject or, worse, accept and misread.
  ///
  /// 0.2 was added to the backend and the bundle advertises the newest version
  /// the backend accepts, so this set staying at `{'0.1'}` disabled Continue on
  /// the first screen against any current deployment — the refusal working
  /// exactly as designed, on a bundle the app could in fact produce. It is here
  /// now because the app emits `carried_forward`, which is the whole of what
  /// 0.2 adds; adding a version to this set without the field it introduces is
  /// the partial compatibility the paragraph above forbids.
  static const supportedSchemaVersions = {'0.1', '0.2'};

  /// The bundle formats this app can read.
  static const supportedBundleFormats = {'1'};

  bool get isUsable =>
      supportedSchemaVersions.contains(schemaVersion) &&
      supportedBundleFormats.contains(bundleFormat);
}
