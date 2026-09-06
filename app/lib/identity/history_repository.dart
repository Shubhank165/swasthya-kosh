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


/// One past visit, for the visits tab — stage 4.
///
/// Everything here is what the hospital recorded, not an interpretation of it.
/// There is deliberately no field for a diagnosis, a report or anything read
/// off a document: §8 keeps unverified extraction away from the patient, and a
/// verified report is the physician's to hand over, not this app's to publish.
class Visit {
  const Visit({
    required this.intakeId,
    required this.receivedAt,
    this.complaint,
    this.department,
    this.seenAt,
  });

  factory Visit.fromJson(Map<String, dynamic> json) => Visit(
        intakeId: json['intake_id'] as String,
        receivedAt:
            DateTime.tryParse(json['received_at']?.toString() ?? '') ?? DateTime.now(),
        complaint: json['complaint'] as String?,
        department: json['department_code'] as String?,
        seenAt: DateTime.tryParse(json['seen_at']?.toString() ?? ''),
      );

  final String intakeId;
  final DateTime receivedAt;

  /// What the patient said was wrong, in their own words where the record kept
  /// them. Null when the visit has no answered complaint — a real state, and
  /// better shown as nothing than as "Unknown".
  final String? complaint;
  final String? department;

  /// When a physician opened it. Null means submitted and not yet seen.
  final DateTime? seenAt;
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

  /// Past visits at this hospital, newest first.
  ///
  /// Same endpoint as [carryForward] and the same failure rule: empty on any
  /// failure. A visits tab that cannot load is a tab with nothing in it, not a
  /// reason to tell a patient something went wrong with their records.
  Future<List<Visit>> visits() async {
    try {
      final response = await _api.get<Map<String, dynamic>>('/patients/me/history');
      if (response.statusCode != 200 || response.data == null) return const [];
      return [
        for (final visit in (response.data!['intakes'] as List<dynamic>? ?? []))
          Visit.fromJson(visit as Map<String, dynamic>),
      ];
    } on Object {
      return const [];
    }
  }
}
