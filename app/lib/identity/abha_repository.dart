/// ABHA linking — 2/3 §7.2.
///
/// **Never mandatory.** The entire app works with a phone number alone (§7.3),
/// and nothing on this path gates an intake: a failed lookup, an unreachable
/// gateway and a patient who taps past the screen all lead to exactly the same
/// place. What linking buys is retrieval — a patient known here under an ABHA
/// address has history to carry forward on screen 5.
///
/// **It is mocked, and the mock says so.** [AbhaLink.isMocked] is what the UI
/// reads to put a notice on screen, so nobody demos a mocked government
/// integration as a live one. That is the same rule the dashboard follows for
/// the same response.
library;

import '../core/api.dart';

class AbhaLink {
  const AbhaLink({
    required this.verified,
    required this.knownHere,
    required this.source,
  });

  factory AbhaLink.fromJson(Map<String, dynamic> json) => AbhaLink(
        verified: json['verified'] as bool? ?? false,
        knownHere: json['known_here'] as bool? ?? false,
        source: json['source'] as String? ?? 'unknown',
      );

  final bool verified;

  /// Whether this hospital already holds records under that address.
  final bool knownHere;

  /// `mock` today. Passed through from the backend verbatim.
  final String source;

  bool get isMocked => source == 'mock';
}

class AbhaRepository {
  AbhaRepository({required ApiClient api}) : _api = api;
  final ApiClient _api;

  /// Offer an address. Null when the attempt could not be made at all.
  ///
  /// Null and `verified: false` are deliberately different: the first is "we
  /// could not ask", the second is "we asked and the answer was no". Neither
  /// stops an intake, but only the second is worth telling the patient about.
  Future<AbhaLink?> link(String address) async {
    try {
      final response = await _api.post<Map<String, dynamic>>(
        '/patients/me/abha',
        body: {'abha_address': address},
      );
      if (response.statusCode != 200 || response.data == null) return null;
      return AbhaLink.fromJson(response.data!);
    } on Object {
      return null;
    }
  }
}
