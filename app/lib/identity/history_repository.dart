/// The returning-patient check — 2/3 §5 screen 5.
///
/// "Our record shows diabetes and Metformin. Still correct?" per item, with
/// Yes / No / Not sure. Never re-asks confirmed history from scratch.
///
/// Two properties of this screen are easy to lose and both matter:
///
/// **It is confirmation, not disclosure.** What comes back is what this
/// hospital already holds and what a physician has already verified — the
/// patient told them, and they are being asked whether it is still true. That
/// is why it does not run into §8's rule against showing extracted values back
/// to a patient: it is not OCR output and it is not an interpretation.
///
/// **"Not sure" is not "no".** A fact the patient doubts is not a fact, and it
/// is certainly not a negative finding. Both "no longer correct" and "not sure"
/// leave the question to be asked normally — only a Yes stops it being asked.
library;

import '../core/api.dart';

class CarriedFact {
  const CarriedFact({
    required this.fieldId,
    required this.label,
    required this.value,
    required this.section,
    required this.intakeId,
    this.verifiedAt,
  });

  factory CarriedFact.fromJson(Map<String, dynamic> json) => CarriedFact(
        fieldId: json['field_id'] as String,
        label: json['label'] as String? ?? json['field_id'] as String,
        value: json['value']?.toString() ?? '',
        section: json['section'] as String? ?? 'history',
        intakeId: json['intake_id'] as String? ?? '',
        verifiedAt: DateTime.tryParse(json['verified_at']?.toString() ?? ''),
      );

  final String fieldId;
  final String label;
  final String value;
  final String section;

  /// The intake this fact was recorded in. Carried so that confirming it in a
  /// later intake can say *which* earlier visit it came from rather than
  /// presenting it as something answered today (schema 0.2).
  final String intakeId;

  /// When a physician verified it. Shown to the patient as the date their
  /// record was last confirmed, which is the only way "still correct?" is a
  /// fair question to ask.
  final DateTime? verifiedAt;
}

class HistoryRepository {
  HistoryRepository({required ApiClient api}) : _api = api;
  final ApiClient _api;

  /// Physician-verified facts this hospital holds for the signed-in patient.
  ///
  /// Empty for a guest, and empty on any failure. A returning-patient screen
  /// that cannot load is a screen that is skipped — the intake asks everything
  /// from scratch, which is slower and completely safe. It must never block.
  Future<List<CarriedFact>> carryForward() async {
    try {
      final response = await _api.get<Map<String, dynamic>>('/patients/me/history');
      if (response.statusCode != 200 || response.data == null) return const [];
      return [
        for (final fact in (response.data!['carry_forward'] as List<dynamic>? ?? []))
          CarriedFact.fromJson(fact as Map<String, dynamic>),
      ];
    } on Object {
      return const [];
    }
  }
}
