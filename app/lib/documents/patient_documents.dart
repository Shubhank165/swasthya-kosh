/// The patient's own document library — stage 4.
///
/// Reads `GET /patients/me/documents`, which is scoped by the session token
/// rather than by anything this app sends. There is no way to ask for somebody
/// else's, because there is nothing to ask with.
///
/// **No extraction crosses this boundary.** The endpoint does not return what
/// was read off a page and this model has nowhere to put it if it did — §8, and
/// the reason the staff route on the intake is a different route rather than
/// the same one with a different guard.
library;

import '../core/api.dart';

class PatientDocument {
  const PatientDocument({
    required this.documentId,
    required this.kind,
    required this.status,
    this.uploadedAt,
    this.rejectionReason,
  });

  factory PatientDocument.fromJson(Map<String, dynamic> json) => PatientDocument(
        documentId: json['document_id'] as String,
        kind: json['kind'] as String? ?? 'other',
        status: json['status'] as String? ?? 'unknown',
        uploadedAt: DateTime.tryParse(json['uploaded_at']?.toString() ?? ''),
        rejectionReason: json['rejection_reason'] as String?,
      );

  final String documentId;

  /// `prescription`, `lab_report`, `discharge_summary`, `other`. A description
  /// of the paper, not of the patient.
  final String kind;
  final String status;
  final DateTime? uploadedAt;

  /// Why the quality gate refused it — blurred, cropped, too dark. About the
  /// photograph, never about its contents.
  final String? rejectionReason;

  bool get rejected => status == 'rejected';
}

class PatientDocumentsRepository {
  PatientDocumentsRepository({required ApiClient api}) : _api = api;

  final ApiClient _api;

  /// Empty on any failure, like the history repository.
  ///
  /// A document tab that cannot load is a tab with nothing in it. It is not a
  /// reason to tell a patient something has gone wrong with their records, and
  /// it must never block anything else in the app.
  Future<List<PatientDocument>> list() async {
    try {
      final response = await _api.get<List<dynamic>>('/patients/me/documents');
      if (response.statusCode != 200 || response.data == null) return const [];
      return [
        for (final row in response.data!)
          PatientDocument.fromJson(row as Map<String, dynamic>),
      ];
    } on Object {
      return const [];
    }
  }
}
