enum KioskStage {
  language,
  registration,
  hub,
  abha,
  who,
  interview,
  ayurveda,
  prakriti,
  documents,
  report,
  emergency,
  consent,
  review,
  finalizing,
  declined,
  unavailable,
}

extension KioskStageExtension on KioskStage {
  String get nameString {
    switch (this) {
      case KioskStage.language:
        return 'language';
      case KioskStage.registration:
        return 'registration';
      case KioskStage.hub:
        return 'hub';
      case KioskStage.abha:
        return 'abha';
      case KioskStage.who:
        return 'who';
      case KioskStage.interview:
        return 'interview';
      case KioskStage.ayurveda:
        return 'ayurveda';
      case KioskStage.prakriti:
        return 'prakriti';
      case KioskStage.documents:
        return 'documents';
      case KioskStage.report:
        return 'report';
      case KioskStage.emergency:
        return 'emergency';
      case KioskStage.consent:
        return 'consent';
      case KioskStage.review:
        return 'review';
      case KioskStage.finalizing:
        return 'finalizing';
      case KioskStage.declined:
        return 'declined';
      case KioskStage.unavailable:
        return 'unavailable';
    }
  }

  static KioskStage fromString(String stage) {
    switch (stage.toLowerCase()) {
      case 'language':
        return KioskStage.language;
      case 'registration':
        return KioskStage.registration;
      case 'hub':
        return KioskStage.hub;
      case 'abha':
        return KioskStage.abha;
      case 'who':
        return KioskStage.who;
      case 'interview':
        return KioskStage.interview;
      case 'ayurveda':
        return KioskStage.ayurveda;
      case 'prakriti':
        return KioskStage.prakriti;
      case 'documents':
        return KioskStage.documents;
      case 'report':
        return KioskStage.report;
      case 'emergency':
        return KioskStage.emergency;
      case 'consent':
        return KioskStage.consent;
      case 'review':
        return KioskStage.review;
      case 'finalizing':
        return KioskStage.finalizing;
      case 'declined':
        return KioskStage.declined;
      default:
        return KioskStage.unavailable;
    }
  }
}

class LanguageItem {
  final String code;
  final String englishName;
  final String nativeName;
  final String greeting;
  final String flagEmoji;
  final String scriptEmblem;

  const LanguageItem({
    required this.code,
    required this.englishName,
    required this.nativeName,
    required this.greeting,
    required this.flagEmoji,
    required this.scriptEmblem,
  });
}

const List<LanguageItem> supportedLanguages = [
  LanguageItem(code: 'hi-IN', englishName: 'Hindi', nativeName: 'हिन्दी', greeting: 'नमस्ते', flagEmoji: '🇮🇳', scriptEmblem: 'अ'),
  LanguageItem(code: 'en-IN', englishName: 'English', nativeName: 'English', greeting: 'Hello', flagEmoji: '🌐', scriptEmblem: 'A'),
  LanguageItem(code: 'mr-IN', englishName: 'Marathi', nativeName: 'मराठी', greeting: 'नमस्कार', flagEmoji: '🇮🇳', scriptEmblem: 'म'),
  LanguageItem(code: 'bn-IN', englishName: 'Bengali', nativeName: 'বাংলা', greeting: 'নমস্কার', flagEmoji: '🇮🇳', scriptEmblem: 'বা'),
  LanguageItem(code: 'te-IN', englishName: 'Telugu', nativeName: 'తెలుగు', greeting: 'నమస్కారం', flagEmoji: '🇮🇳', scriptEmblem: 'తె'),
  LanguageItem(code: 'ta-IN', englishName: 'Tamil', nativeName: 'தமிழ்', greeting: 'வணக்கம்', flagEmoji: '🇮🇳', scriptEmblem: 'த'),
  LanguageItem(code: 'gu-IN', englishName: 'Gujarati', nativeName: 'ગુજરાતી', greeting: 'નમસ્તે', flagEmoji: '🇮🇳', scriptEmblem: 'ગુ'),
  LanguageItem(code: 'kn-IN', englishName: 'Kannada', nativeName: 'ಕನ್ನಡ', greeting: 'ನಮಸ್ಕಾರ', flagEmoji: '🇮🇳', scriptEmblem: 'ಕ'),
  LanguageItem(code: 'pa-IN', englishName: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', greeting: 'ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ', flagEmoji: '🇮🇳', scriptEmblem: 'ਪ'),
];

class PatientProfile {
  String name;
  int? age;
  String gender; // Male, Female, Other
  String? abhaNumber;
  String? mobileNumber;
  bool isWalkIn;

  PatientProfile({
    this.name = 'Patient / मरीज़',
    this.age = 35,
    this.gender = 'Male',
    this.abhaNumber,
    this.mobileNumber,
    this.isWalkIn = true,
  });

  PatientProfile copyWith({
    String? name,
    int? age,
    String? gender,
    String? abhaNumber,
    String? mobileNumber,
    bool? isWalkIn,
  }) {
    return PatientProfile(
      name: name ?? this.name,
      age: age ?? this.age,
      gender: gender ?? this.gender,
      abhaNumber: abhaNumber ?? this.abhaNumber,
      mobileNumber: mobileNumber ?? this.mobileNumber,
      isWalkIn: isWalkIn ?? this.isWalkIn,
    );
  }

  String get maskedAbha {
    if (abhaNumber == null || abhaNumber!.isEmpty) return 'Walk-in (No ABHA)';
    final clean = abhaNumber!.replaceAll('-', '').replaceAll(' ', '');
    if (clean.length < 4) return clean;
    final last4 = clean.substring(clean.length - 4);
    return '••-••••-••••-$last4';
  }
}

class ClinicalAnswerRecord {
  final String questionText;
  final String answerText;
  final DateTime timestamp;
  final String? questionId;

  ClinicalAnswerRecord({
    required this.questionText,
    required this.answerText,
    required this.timestamp,
    this.questionId,
  });
}

class PatientStateModel {
  String? complaint;
  String? duration;
  int? severity;
  bool? breathlessness;
  bool? painRadiation;
  bool? sweating;
  bool? vomiting;
  bool? fever;
  bool? activeBleeding;
  int? ageYears;

  PatientStateModel({
    this.complaint,
    this.duration,
    this.severity,
    this.breathlessness,
    this.painRadiation,
    this.sweating,
    this.vomiting,
    this.fever,
    this.activeBleeding,
    this.ageYears,
  });

  factory PatientStateModel.fromJson(Map<String, dynamic> json) {
    return PatientStateModel(
      complaint: json['complaint'] as String?,
      duration: json['duration'] as String?,
      severity: json['severity'] as int?,
      breathlessness: json['breathlessness'] as bool?,
      painRadiation: json['pain_radiation'] as bool?,
      sweating: json['sweating'] as bool?,
      vomiting: json['vomiting'] as bool?,
      fever: json['fever'] as bool?,
      activeBleeding: json['active_bleeding'] as bool?,
      ageYears: json['age_years'] as int?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'complaint': complaint,
      'duration': duration,
      'severity': severity,
      'breathlessness': breathlessness,
      'pain_radiation': painRadiation,
      'sweating': sweating,
      'vomiting': vomiting,
      'fever': fever,
      'active_bleeding': activeBleeding,
      'age_years': ageYears,
    };
  }
}
