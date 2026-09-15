/// Deleting everything the hospital holds about this patient.
///
/// The one destructive call this app can make. It takes no argument on purpose:
/// the patient it erases comes from the session token, so there is no identifier
/// to get wrong and no way to aim it at somebody else.
///
/// **Not queued.** Every other write in this app goes through `submit/queue.dart`
/// so a patient in a basement does not lose their answers. Deletion is the
/// opposite case: a queued erasure would tell somebody their record was gone
/// while it sat on the device waiting for signal, and they would walk away
/// believing it. This one call needs the network, and says so when it does not
/// have it.
library;

import '../core/api.dart';

/// What an erasure removed, as the backend counted it.
///
/// Counts rather than a bare success, so the screen can say "3 visits and 2
/// documents deleted" — a sentence the patient can check against what they
/// remember. A silent "done" is not checkable.
class ErasureSummary {
  const ErasureSummary({
    required this.intakes,
    required this.documents,
    required this.ayushProfiles,
    required this.complete,
  });

  factory ErasureSummary.fromJson(Map<String, dynamic> json) => ErasureSummary(
        intakes: (json['intakes'] as num?)?.toInt() ?? 0,
        documents: (json['documents'] as num?)?.toInt() ?? 0,
        ayushProfiles: (json['ayush_profiles'] as num?)?.toInt() ?? 0,
        complete: json['complete'] as bool? ?? false,
      );

  final int intakes;
  final int documents;
  final int ayushProfiles;

  /// False when a scanned document could not be removed from storage. The rows
  /// are gone either way; the image is not, and a screen that said "deleted"
  /// over the top of that would be a lie the patient cannot detect.
  final bool complete;

  bool get erasedNothing => intakes == 0 && documents == 0 && ayushProfiles == 0;
}

class ErasureRepository {
  ErasureRepository({required ApiClient api}) : _api = api;
  final ApiClient _api;

  /// Erase this patient's record. Null when the request could not be made.
  ///
  /// Null and a summary are deliberately different, and the screen must treat
  /// them differently: null is "we could not ask, nothing has been deleted",
  /// which a patient has to be told plainly so they try again. Reporting a
  /// failed delete as a success is the worst outcome this screen has.
  Future<ErasureSummary?> eraseHistory() async {
    try {
      final response = await _api.delete<Map<String, dynamic>>(
        '/patients/me/history',
      );
      if (response.statusCode != 200 || response.data == null) return null;
      return ErasureSummary.fromJson(response.data!);
    } on Object {
      return null;
    }
  }
}
