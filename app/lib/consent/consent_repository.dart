/// The consent notice, and the artefact it produces — 2/3 §11.
///
/// Consent here is a **record you could produce in an audit**, matching the
/// backend's artefact from 1/3: the exact text shown, the language it was shown
/// in, the purposes granted, the purposes refused, when, and who granted it.
/// Not a boolean. A boolean would not survive one question from a regulator,
/// and it would not survive one from a patient either.
///
/// The notice text is content, served by the backend from
/// `clinical/consent/consent_v1.yaml`. It is not a string in this app, and it
/// must never become one: the artefact stores a hash of what was shown, and
/// text that lives in two places is text that will eventually differ from the
/// hash of itself.
library;

import '../core/api.dart';

class ConsentPurposeSpec {
  const ConsentPurposeSpec({
    required this.code,
    required this.required,
    required this.label,
    required this.description,
  });

  factory ConsentPurposeSpec.fromJson(Map<String, dynamic> json) =>
      ConsentPurposeSpec(
        code: json['code'] as String,
        required: json['required'] as bool? ?? false,
        label: Map<String, String>.from(
          (json['label'] as Map<String, dynamic>? ?? {})
              .map((k, v) => MapEntry(k, v.toString())),
        ),
        description: Map<String, String>.from(
          (json['description'] as Map<String, dynamic>? ?? {})
              .map((k, v) => MapEntry(k, v.toString())),
        ),
      );

  final String code;
  final bool required;
  final Map<String, String> label;
  final Map<String, String> description;

  /// The label in [language], or null when it is not translated.
  ///
  /// Null rather than an English fallback, deliberately. Agreement to a notice
  /// in a language the patient did not choose is not consent, and showing one
  /// would put a signature under text they could not read.
  String? labelFor(String language) => label[language];
  String? descriptionFor(String language) => description[language];
}

class ConsentNotice {
  const ConsentNotice({required this.version, required this.purposes});

  factory ConsentNotice.fromJson(Map<String, dynamic> json) => ConsentNotice(
        version: json['consent_version'] as String? ?? '1',
        purposes: [
          for (final purpose in (json['purposes'] as List<dynamic>? ?? []))
            ConsentPurposeSpec.fromJson(purpose as Map<String, dynamic>),
        ],
      );

  final String version;
  final List<ConsentPurposeSpec> purposes;

  /// Only the purposes this app can show in [language].
  List<ConsentPurposeSpec> readableIn(String language) =>
      [for (final p in purposes) if (p.labelFor(language) != null) p];

  /// True when everything the intake depends on can be read in [language].
  ///
  /// When it is false the patient cannot lawfully be asked, and the caller must
  /// not fall back to English — see [ConsentPurposeSpec.labelFor].
  bool isCompleteIn(String language) =>
      purposes.where((p) => p.required).every((p) => p.labelFor(language) != null);

  /// Exactly what was put on the screen, as one document.
  ///
  /// This is the string the artefact stores and hashes. Assembled from the same
  /// fields the screen renders, in the same order, so "what was shown" and
  /// "what was recorded" cannot drift apart.
  String noticeTextIn(String language) => [
        for (final purpose in readableIn(language))
          '${purpose.labelFor(language)}\n${purpose.descriptionFor(language) ?? ''}'
              .trim(),
      ].join('\n\n');
}

class ConsentRepository {
  ConsentRepository({required ApiClient api}) : _api = api;
  final ApiClient _api;

  /// The notice for **this** surface.
  ///
  /// `source=app` matters: the kiosk's notice includes a purpose about keeping
  /// a recording of the patient's voice, and this app has no microphone. Asking
  /// for that consent here would file an artefact describing something that did
  /// not happen, for every intake.
  Future<ConsentNotice?> load() async {
    final response =
        await _api.get<Map<String, dynamic>>('/content/consent', query: {'source': 'app'});
    if (response.statusCode != 200 || response.data == null) return null;
    return ConsentNotice.fromJson(response.data!);
  }
}

/// What the patient agreed to, ready to file against an intake.
///
/// Built when the patient taps through the consent screen and posted **after**
/// the intake record has been accepted — the artefact references an intake, and
/// an artefact against an intake the backend has never seen is a dangling row
/// that nothing can produce in an audit.
class ConsentGrant {
  const ConsentGrant({
    required this.consentVersion,
    required this.language,
    required this.noticeText,
    required this.granted,
    required this.refused,
    required this.grantingParty,
  });

  factory ConsentGrant.fromJson(Map<String, dynamic> json) => ConsentGrant(
        consentVersion: json['consent_version'] as String,
        language: json['language'] as String,
        noticeText: json['notice_text'] as String,
        granted: [for (final c in json['granted_purposes'] as List<dynamic>) c.toString()],
        refused: [for (final c in json['refused_purposes'] as List<dynamic>) c.toString()],
        grantingParty: json['granting_party'] as String,
      );

  final String consentVersion;
  final String language;

  /// The full text shown, which the backend hashes. Sent rather than the hash
  /// so the artefact holds the document itself.
  final String noticeText;
  final List<String> granted;

  /// Named, not inferred from absence. "Refused" and "never offered" are
  /// different things to a regulator, and the difference is exactly the kind a
  /// boolean loses.
  final List<String> refused;

  /// `self` / `parent_guardian` / … — the reporter, since that is who is
  /// standing there tapping.
  final String grantingParty;

  Map<String, dynamic> toJson() => {
        'consent_version': consentVersion,
        'language': language,
        'notice_text': noticeText,
        'granted_purposes': granted,
        'refused_purposes': refused,
        'granting_party': grantingParty,
      };
}
