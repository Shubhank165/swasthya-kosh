/// Assembling the v0.1 record the backend ingests — 2/3 §9.
///
/// **The app produces the same JSON the Jetson produces**, against the same
/// versioned contract, posted to the same endpoint. One schema, one door.
///
/// The differences are exactly the ones §9 lists and no others:
///
/// - `source` is `"app"` and `kiosk_id` is null.
/// - `app_version` travels alongside `engine_version`.
/// - The voice-specific turn fields — `transcript`, `asr_confidence`, `rms` —
///   are **null rather than absent**, so the contract keeps one shape and the
///   normalizer needs no branch for where a record came from.
///
/// There is no `confidence` on an app field, and that is deliberate rather than
/// an omission: a tap has no confidence to report. The Jetson's confidence is a
/// property of speech recognition, and inventing a `1.0` here would make a
/// tapped answer look like a perfectly-heard spoken one to every downstream
/// consumer, including the OCR confidence floor's sibling checks.
library;

import '../content/answer.dart';
import '../content/bundle.dart';

class PatientRef {
  const PatientRef({required this.type, this.value});
  const PatientRef.guest() : type = 'guest', value = null;

  /// `phone` is how the app identifies a patient. The value is the opaque
  /// reference the sign-in returned — a peppered HMAC, not the number.
  const PatientRef.phone(String reference) : type = 'phone', value = reference;

  final String type;
  final String? value;

  Map<String, dynamic> toJson() => {'type': type, 'value': value};
}

class IntakeRecordBuilder {
  IntakeRecordBuilder({
    required this.intakeId,
    required this.hospitalId,
    required this.bundle,
    required this.language,
    required this.reporter,
    required this.appVersion,
    this.departmentCode,
    this.patientRef = const PatientRef.guest(),
  });

  final String intakeId;
  final String hospitalId;
  final ContentBundle bundle;
  final String language;

  /// `self` / `parent_guardian` / `family_attendant` / `caregiver` / `staff`.
  final String reporter;
  final String appVersion;
  final String? departmentCode;
  final PatientRef patientRef;

  /// Build the record.
  ///
  /// [abortedByRedFlag] switches the status to `aborted_red_flag` and carries
  /// the rule that fired (§6.3). The record is submitted **partial** in that
  /// case — everything answered up to the flag — because a patient being sent
  /// to an emergency department is exactly when the hospital most wants the
  /// answers that sent them there.
  Map<String, dynamic> build({
    required Map<String, Answer> answers,
    required DateTime startedAt,
    required DateTime completedAt,
    RedFlagHitRecord? abortedByRedFlag,
  }) {
    final turns = <Map<String, dynamic>>[];
    final fields = <String, dynamic>{};

    var turnId = 0;
    for (final answer in answers.values) {
      // Only questions that were actually put become turns. A `not_asked` field
      // has no turn by definition, and inventing one would claim the patient
      // was shown a question they never saw.
      //
      // `answer.wasPut` is the load-bearing half and is not redundant with the
      // statuses beside it: a fact carried forward from an earlier visit and
      // confirmed on screen 5 is `answered`, and it was never asked here. A
      // turn for it would put a prompt with `asked_text: null` into the record
      // and claim this interview showed it.
      final wasPut = answer.wasPut &&
          answer.status != FieldStatus.notAsked &&
          answer.status != FieldStatus.notApplicable;
      int? sourceTurn;
      if (wasPut) {
        turnId += 1;
        sourceTurn = turnId;
        turns.add({
          'turn_id': turnId,
          'question_id': answer.questionId,
          // The prompt actually shown, in the language actually used (§9).
          'asked_text': answer.askedText,
          // Null, not absent. One contract shape for both sources.
          'transcript': null,
          'asr_confidence': null,
          'rms': null,
          'bound_field': answer.fieldId,
          'bound_value':
              answer.status == FieldStatus.answered ? answer.value?.toJson() : null,
          'resolved': answer.status == FieldStatus.answered,
        });
      }
      fields[answer.fieldId] = answer.toFieldJson(sourceTurn: sourceTurn);
    }

    return {
      'schema_version': bundle.schemaVersion,
      'intake_id': intakeId,
      'source': 'app',
      'kiosk_id': null,
      'app_version': appVersion,
      'hospital_id': hospitalId,
      'started_at': startedAt.toIso8601String(),
      'completed_at': completedAt.toIso8601String(),
      'status': abortedByRedFlag == null ? 'complete' : 'aborted_red_flag',
      'language': language,
      // The app locks the language at the first screen and never changes it
      // mid-intake, so there is no turn at which it was locked.
      'language_locked_at_turn': null,
      'reporter': reporter,
      'department_code': departmentCode,
      'patient_ref': patientRef.toJson(),
      'turns': turns,
      'fields': fields,
      'red_flags': [
        if (abortedByRedFlag != null) abortedByRedFlag.toJson(),
      ],
      // The app has no interview engine. Naming one would claim a component
      // that is not running.
      'engine_version': null,
      'content_version': bundle.contentVersion,
    };
  }
}

/// A red flag as it travels in the record — §6.3.
///
/// Carries the rule id, the answers that triggered it and when. It does **not**
/// carry a label or any interpretation: the backend already refuses to
/// re-evaluate rules, and a phrase invented here would end up on a physician's
/// screen looking like a finding.
class RedFlagHitRecord {
  const RedFlagHitRecord({
    required this.ruleId,
    required this.severity,
    required this.firedAt,
    required this.fields,
  });

  final String ruleId;
  final String severity;
  final DateTime firedAt;
  final Map<String, String> fields;

  Map<String, dynamic> toJson() => {
        'rule_id': ruleId,
        'severity': severity,
        'fired_at': firedAt.toIso8601String(),
        'triggering_fields': fields,
      };
}
