/// Suggests answers to upcoming structured questions from a free-text one.
///
/// **A suggestion is never an answer.** This repository's whole output is a
/// value a not-yet-shown screen may pre-fill; nothing it returns touches
/// [IntakeWalker] or the record, and a call that fails, times out, or comes
/// back empty changes nothing about how the interview proceeds — the question
/// is simply put to the patient, exactly as it would be with no provider
/// configured at all. See `IntakeFlow._requestPrefill`, which is the only
/// caller.
///
/// Calling Gemini here means the patient's free-text answer leaves the device
/// before the interview is done — the same trade-off `RepairProvider` and
/// `TimelineProvider` already make on the backend, made once more on this one
/// path. Nothing else the walker asks is sent anywhere until the intake is
/// submitted.
library;

import '../content/answer.dart';
import '../content/bundle.dart';
import '../core/api.dart';
import '../core/logging.dart';

class PrefillRepository {
  PrefillRepository({required ApiClient api}) : _api = api;
  final ApiClient _api;

  /// Ask for suggestions against [pending], from [freeText] — the patient's
  /// own words, already recorded as their answer to a free-text question.
  ///
  /// Best-effort, always: returns an empty map on any failure — a timeout, a
  /// non-200, an unreadable body — because the caller's fallback in every case
  /// is simply to put the question normally, which needs no signal from this
  /// beyond "no suggestion". Never retried; a patient waiting on a screen that
  /// has not moved is a worse outcome than one missed suggestion.
  Future<Map<String, AnswerValue>> suggest({
    required String intakeId,
    required String language,
    required String freeText,
    required List<Question> pending,
  }) async {
    if (freeText.trim().isEmpty || pending.isEmpty) return const {};
    try {
      final response = await _api.post<Map<String, dynamic>>(
        '/intakes/$intakeId/prefill',
        body: {
          'free_text': freeText,
          'questions': [for (final question in pending) _questionPayload(question, language)],
        },
      );
      if (response.statusCode != 200 || response.data == null) return const {};
      final raw = response.data!['suggestions'] as List<dynamic>? ?? const [];
      final result = <String, AnswerValue>{};
      for (final entry in raw) {
        if (entry is! Map<String, dynamic>) continue;
        final fieldId = entry['field_id'] as String?;
        if (fieldId == null) continue;
        final value = answerValueFromDraft(entry['kind'] as String?, entry['value']);
        if (value != null) result[fieldId] = value;
      }
      return result;
    } on Object catch (error) {
      // Never surfaced to the patient. No clinical text in the log line — the
      // same rule `ApiClient` itself follows for every request it makes.
      logEvent('prefill_failed', fields: {'type': error.runtimeType.toString()});
      return const {};
    }
  }

  Map<String, dynamic> _questionPayload(Question question, String language) => {
        'field_id': question.fieldId,
        'answer_type': _wireAnswerType(question.answerType),
        'prompt': question.promptFor(language) ?? '',
        if (question.options != null) 'options': question.options,
        if (question.unit != null) 'unit': question.unit,
        if (question.minimum != null) 'min': question.minimum,
        if (question.maximum != null) 'max': question.maximum,
      };
}

/// The wire name for [type] — the inverse of [AnswerType.parse].
String _wireAnswerType(AnswerType type) => switch (type) {
      AnswerType.singleChoice => 'single_choice',
      AnswerType.multiChoice => 'multi_choice',
      AnswerType.yesNoUnknown => 'yes_no_unknown',
      AnswerType.number => 'number',
      AnswerType.scale => 'scale',
      AnswerType.duration => 'duration',
      AnswerType.date => 'date',
      AnswerType.freeText => 'free_text',
      AnswerType.unknown => 'unknown',
    };
