import '../models/models.dart';

class VerbalMatchResult {
  final bool matched;
  final String action;
  final dynamic value;

  const VerbalMatchResult({
    required this.matched,
    required this.action,
    this.value,
  });

  static const none = VerbalMatchResult(matched: false, action: 'none');

  /// The same match reported under a different action name.
  ///
  /// Lets one matcher serve two questionnaires: both answer from the options the server put on
  /// screen, but the controller has to send the answer back on the right command.
  VerbalMatchResult asAction(String newAction) => matched
      ? VerbalMatchResult(matched: true, action: newAction, value: value)
      : this;
}

class VerbalOptionMatcher {
  /// Evaluates spoken transcript against the current screen context
  /// and determines if any option was verbally requested.
  static VerbalMatchResult match({
    required String transcript,
    required KioskStage currentStage,
    String? questionId,
    /// Options exactly as the server sent them: `{value, label, icon}`. Previously a
    /// hardcoded Dart questionnaire, which drifted from the server's own list.
    List<Map<String, dynamic>> ayurvedaOptions = const [],
  }) {
    final text = transcript.toLowerCase().trim();
    if (text.isEmpty) return VerbalMatchResult.none;

    // Global navigation commands
    if (text == 'back' ||
        text.contains('पीछे') ||
        text.contains('peeche') ||
        text.contains('peche') ||
        text == 'wapas' ||
        text.contains('go back')) {
      return const VerbalMatchResult(matched: true, action: 'back');
    }
    if (text.contains('restart') ||
        text.contains('नया मरीज़') ||
        text.contains('reset') ||
        text.contains('naya mareez') ||
        text.contains('new patient')) {
      return const VerbalMatchResult(matched: true, action: 'restart');
    }

    switch (currentStage) {
      case KioskStage.consent:
      case KioskStage.review:
      case KioskStage.finalizing:
      case KioskStage.declined:
      case KioskStage.unavailable:
        return VerbalMatchResult.none; // Protocol 2 dispatches only on the backend.
      case KioskStage.language:
        return _matchLanguage(text);

      case KioskStage.who:
        return _matchWho(text);

      case KioskStage.registration:
      case KioskStage.hub:
      case KioskStage.abha:
        if (text.contains('skip') ||
            text.contains('छोड़ें') ||
            text.contains('aage') ||
            text.contains('chodo') ||
            text.contains('chod') ||
            text.contains('nahi hai') ||
            text == 'next') {
          return const VerbalMatchResult(matched: true, action: 'next');
        }
        break;

      case KioskStage.interview:
        return _matchInterview(text, questionId);

      case KioskStage.ayurveda:
        return _matchAyurveda(text, questionId, ayurvedaOptions);

      case KioskStage.prakriti:
        // Same matcher: it works off the options the server put on screen, so it needs to know
        // nothing about which questionnaire is being asked. That covers the opening
        // "have you filled this before?" screen too - it is a two-option choice like any other.
        return _matchAyurveda(text, questionId, ayurvedaOptions)
            .asAction('prakriti_option');

      case KioskStage.documents:
        if (text.contains('done') ||
            text.contains('हो गया') ||
            text.contains('ho gaya') ||
            text.contains('aage') ||
            text.contains('skip') ||
            text == 'next') {
          return const VerbalMatchResult(matched: true, action: 'next');
        }
        if (text.contains('scan') || text.contains('स्कैन') || text.contains('photo') || text.contains('camera')) {
          return const VerbalMatchResult(matched: true, action: 'scan');
        }
        break;

      case KioskStage.report:
      case KioskStage.emergency:
        if (text.contains('new') ||
            text.contains('नया') ||
            text.contains('start') ||
            text.contains('theek') ||
            text.contains('finish') ||
            text.contains('done')) {
          return const VerbalMatchResult(matched: true, action: 'restart');
        }
        break;
    }

    return VerbalMatchResult.none;
  }

  static VerbalMatchResult _matchLanguage(String text) {
    if (text.contains('hindi') || text.contains('हिन्दी') || text.contains('हिंदी') || text.contains('नमस्ते')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'hi-IN');
    }
    if (text.contains('english') || text.contains('अंग्रेजी') || text.contains('hello')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'en-IN');
    }
    if (text.contains('bengali') || text.contains('bangla') || text.contains('বাংলা')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'bn-IN');
    }
    if (text.contains('marathi') || text.contains('मराठी')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'mr-IN');
    }
    if (text.contains('telugu') || text.contains('తెలుగు')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'te-IN');
    }
    if (text.contains('tamil') || text.contains('தமிழ்') || text.contains('vanakkam')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'ta-IN');
    }
    if (text.contains('gujarati') || text.contains('ગુજરાતી')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'gu-IN');
    }
    if (text.contains('kannada') || text.contains('ಕನ್ನಡ')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'kn-IN');
    }
    if (text.contains('punjabi') || text.contains('ਪੰਜਾਬੀ')) {
      return const VerbalMatchResult(matched: true, action: 'language', value: 'pa-IN');
    }
    return VerbalMatchResult.none;
  }

  static VerbalMatchResult _matchWho(String text) {
    if (text.contains('self') ||
        text.contains('patient') ||
        text.contains('स्वयं') ||
        text.contains('खुद') ||
        text.contains('main') ||
        text.contains('mera') ||
        text.contains('meri') ||
        text.contains('mere') ||
        text.contains('apne') ||
        text.contains('mujhe')) {
      return const VerbalMatchResult(matched: true, action: 'who', value: 'self');
    }
    if (text.contains('other') ||
        text.contains('someone') ||
        text.contains('किसी और') ||
        text.contains('kisi aur') ||
        text.contains('baccha') ||
        text.contains('child') ||
        text.contains('mata') ||
        text.contains('pita') ||
        text.contains('dusra') ||
        text.contains('doosra') ||
        text.contains('family')) {
      return const VerbalMatchResult(matched: true, action: 'who', value: 'other');
    }
    return VerbalMatchResult.none;
  }

  static VerbalMatchResult _matchInterview(String text, String? questionId) {
    // 1. Check for explicit Option numbers (works across all multiline cards)
    final optNum = _matchOptionNumber(text);

    // 2. Duration Stage
    if (questionId == 'ask_duration') {
      if (optNum == 0 || text.contains('aaj') || text.contains('today') || text.contains('abhi') || text.contains('subah se') || text.contains('kal se')) {
        return const VerbalMatchResult(matched: true, action: 'duration', value: 'today');
      }
      if (optNum == 1 || text.contains('do din') || text.contains('teen din') || text.contains('three days') || text.contains('two days') || text.contains('few days') || text.contains('chaar din')) {
        return const VerbalMatchResult(matched: true, action: 'duration', value: 'three days');
      }
      if (optNum == 2 || text.contains('hafta') || text.contains('week') || text.contains('ek hafta') || text.contains('do hafte') || text.contains('several days')) {
        return const VerbalMatchResult(matched: true, action: 'duration', value: 'one week');
      }
      if (optNum == 3 || text.contains('mahina') || text.contains('month') || text.contains('mahine') || text.contains('bahut dino se') || text.contains('purani')) {
        return const VerbalMatchResult(matched: true, action: 'duration', value: 'one month');
      }
    }

    // 3. Severity Stage (FACES 0 to 10)
    if (questionId == 'ask_severity') {
      if (text.contains('zero') || text.contains('shunya') || text.contains('dard nahi') || text.contains('bilkul nahi') || text.contains('no hurt') || text == '0') {
        return const VerbalMatchResult(matched: true, action: 'severity', value: 0);
      }
      if (text.contains('do') || text.contains('two') || text.contains('bahut halka') || text.contains('halka sa') || text == '2') {
        return const VerbalMatchResult(matched: true, action: 'severity', value: 2);
      }
      if (text.contains('chaar') || text.contains('four') || text.contains('thoda dard') || text.contains('thoda sa') || text == '4') {
        return const VerbalMatchResult(matched: true, action: 'severity', value: 4);
      }
      if (text.contains('chhe') || text.contains('six') || text.contains('madhyam') || text.contains('kaafi dard') || text == '6') {
        return const VerbalMatchResult(matched: true, action: 'severity', value: 6);
      }
      if (text.contains('aath') || text.contains('eight') || text.contains('bahut dard') || text.contains('tez dard') || text == '8') {
        return const VerbalMatchResult(matched: true, action: 'severity', value: 8);
      }
      if (text.contains('das') || text.contains('ten') || text.contains('asahania') || text.contains('asahneey') || text.contains('worst') || text.contains('sabse tez') || text == '10') {
        return const VerbalMatchResult(matched: true, action: 'severity', value: 10);
      }
    }

    // 4. Binary YES / NO Questions (Breathlessness, Radiation, Sweating, Vomiting, Fever, Bleeding)
    if (_isYesNoQuestion(questionId)) {
      // Check negative FIRST so phrases like "dikkat nahi hai" are not caught as affirmative
      if (_isNegative(text) || optNum == 1) {
        return const VerbalMatchResult(matched: true, action: 'yes_no', value: false);
      }
      if (_isAffirmative(text) || optNum == 0) {
        return const VerbalMatchResult(matched: true, action: 'yes_no', value: true);
      }
    }

    // 5. Age Question
    if (questionId == 'ask_age') {
      if (optNum == 0 || text.contains('baccha') || text.contains('child') || text.contains('das')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: '10 years');
      }
      if (optNum == 1 || text.contains('yuva') || text.contains('young') || text.contains('pachees') || text.contains('25')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: '25 years');
      }
      if (optNum == 2 || text.contains('vayask') || text.contains('adult') || text.contains('paintalees') || text.contains('45')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: '45 years');
      }
      if (optNum == 3 || text.contains('varishth') || text.contains('senior') || text.contains('bujurg') || text.contains('old') || text.contains('65')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: '65 years');
      }
    }

    // 6. Chief Complaint Stage
    if (questionId == null || questionId == 'ask_complaint') {
      if (text.contains('chest') || text.contains('dil') || text.contains('seena') || text.contains('chhati') || text.contains('chati')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: 'severe chest pain');
      }
      if (text.contains('pet') || text.contains('stomach') || text.contains('belly') || text.contains('abdomen') || text.contains('gas')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: 'severe stomach abdominal pain');
      }
      if (text.contains('sir') || text.contains('head') || text.contains('sar') || text.contains('chakkar') || text.contains('matha')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: 'severe headache and dizziness');
      }
      if (text.contains('saans') || text.contains('breath') || text.contains('saas') || text.contains('dam')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: 'difficulty breathing shortness of breath');
      }
      if (text.contains('bukhar') || text.contains('fever') || text.contains('tap') || text.contains('thand lag')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: 'high fever and chills');
      }
      if (text.contains('ulti') || text.contains('vomit') || text.contains('dast') || text.contains('matli')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: 'vomiting and diarrhea');
      }
      if (text.contains('pair') || text.contains('leg') || text.contains('ghutna') || text.contains('joint') || text.contains('jod')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: 'severe leg and knee joint pain');
      }
      if (text.contains('kamar') || text.contains('back') || text.contains('peeth')) {
        return const VerbalMatchResult(matched: true, action: 'complaint', value: 'severe lower back pain');
      }
    }

    return VerbalMatchResult.none;
  }

  static VerbalMatchResult _matchAyurveda(
    String text,
    String? questionId,
    List<Map<String, dynamic>> options,
  ) {
    // 1. Direct option number reference ("option 1", "pehla", "first", "1", etc.)
    final optNum = _matchOptionNumber(text);
    if (optNum != null) {
      return VerbalMatchResult(matched: true, action: 'ayurveda_option', value: optNum);
    }

    // 2. Match against the options the server actually put on screen. The label already
    // arrives in the patient's chosen language, so this works for every supported language
    // rather than only the two that were hardcoded.
    for (int i = 0; i < options.length; i++) {
      final value = (options[i]['value'] as String? ?? '').toLowerCase();
      final label = (options[i]['label'] as String? ?? '').toLowerCase();

      if (value.isNotEmpty && text.contains(value)) {
        return VerbalMatchResult(matched: true, action: 'ayurveda_option', value: i);
      }

      final keywords = label
          .split(RegExp(r'[, /]+'))
          .where((w) => w.length > 2 && !['and', 'the', 'है', 'का', 'की', 'के'].contains(w));
      for (final keyword in keywords) {
        if (text.contains(keyword)) {
          return VerbalMatchResult(matched: true, action: 'ayurveda_option', value: i);
        }
      }
    }

    // 3. Broad Ayurveda keyword matching
    // Vata / Option 0 keywords
    if (text.contains('patla') ||
        text.contains('thin') ||
        text.contains('sukhi') ||
        text.contains('dry') ||
        text.contains('rukhi') ||
        text.contains('thand') ||
        text.contains('cold') ||
        text.contains('kacchi') ||
        text.contains('light') ||
        text.contains('anxious') ||
        text.contains('ghabrahat') ||
        text.contains('bechaini') ||
        text.contains('shakahari') ||
        text.contains('veg')) {
      return const VerbalMatchResult(matched: true, action: 'ayurveda_option', value: 0);
    }

    // Pitta / Option 1 keywords
    if (text.contains('madhyam') ||
        text.contains('medium') ||
        text.contains('garmi') ||
        text.contains('hot') ||
        text.contains('warm') ||
        text.contains('gussa') ||
        text.contains('angry') ||
        text.contains('chidchida') ||
        text.contains('moderate') ||
        text.contains('normal') ||
        text.contains('non veg') ||
        text.contains('mixed')) {
      return const VerbalMatchResult(matched: true, action: 'ayurveda_option', value: 1);
    }

    // Kapha / Option 2 keywords
    if (text.contains('bhaari') ||
        text.contains('heavy') ||
        text.contains('mota') ||
        text.contains('mulayam') ||
        text.contains('soft') ||
        text.contains('gehri') ||
        text.contains('deep') ||
        text.contains('quiet') ||
        text.contains('chup') ||
        text.contains('barish') ||
        text.contains('damp')) {
      return const VerbalMatchResult(matched: true, action: 'ayurveda_option', value: 2);
    }

    // Option 3 keywords (Appetite: Poor / Heaviness)
    if (text.contains('kamzor') || text.contains('poor') || text.contains('bhaari lagta') || text.contains('pachta nahi')) {
      return const VerbalMatchResult(matched: true, action: 'ayurveda_option', value: 3);
    }

    return VerbalMatchResult.none;
  }

  /// Extracts option number from phrases like "option 1", "first", "pehla", etc.
  static int? _matchOptionNumber(String text) {
    if (text.contains('pehla') ||
        text.contains('pahla') ||
        text.contains('first') ||
        text.contains('ek number') ||
        text.contains('option 1') ||
        text.contains('option ek') ||
        text.contains('number 1') ||
        text == '1' ||
        text == 'one' ||
        text == 'ek') {
      return 0;
    }
    if (text.contains('doosra') ||
        text.contains('dusra') ||
        text.contains('second') ||
        text.contains('do number') ||
        text.contains('option 2') ||
        text.contains('option do') ||
        text.contains('number 2') ||
        text == '2' ||
        text == 'two' ||
        text == 'do') {
      return 1;
    }
    if (text.contains('teesra') ||
        text.contains('tisra') ||
        text.contains('third') ||
        text.contains('teen number') ||
        text.contains('option 3') ||
        text.contains('option teen') ||
        text.contains('number 3') ||
        text == '3' ||
        text == 'three' ||
        text == 'teen') {
      return 2;
    }
    if (text.contains('chautha') ||
        text.contains('fourth') ||
        text.contains('chaar number') ||
        text.contains('option 4') ||
        text.contains('option chaar') ||
        text.contains('number 4') ||
        text == '4' ||
        text == 'four' ||
        text == 'chaar') {
      return 3;
    }
    return null;
  }

  static bool _isYesNoQuestion(String? qId) {
    const yesNoList = [
      'ask_breathlessness',
      'ask_radiation',
      'ask_sweating',
      'ask_vomiting',
      'ask_fever',
      'ask_bleeding',
    ];
    return qId != null && yesNoList.contains(qId);
  }

  static bool _isNegative(String text) {
    return text.contains('nahin') ||
        text.contains('nahi') ||
        text.contains('नहीं') ||
        text.contains('naa') ||
        text.contains('no') ||
        text.contains('kuch nahi') ||
        text.contains('bilkul nahi') ||
        text.contains('koi nahi') ||
        text.contains('kabhi nahi') ||
        text.contains('theek hai koi dikkat nahi') ||
        text == 'n' ||
        text == 'na' ||
        text == 'nope';
  }

  static bool _isAffirmative(String text) {
    // If negative is present, do NOT treat as affirmative!
    if (_isNegative(text)) return false;

    return text.contains('haan') ||
        text.contains('हाँ') ||
        text.contains('yes') ||
        text.contains('ha ') ||
        text == 'ha' ||
        text.contains('bilkul') ||
        text.contains('sahi') ||
        text.contains('ho raha') ||
        text.contains('aa raha') ||
        text.contains('lag raha') ||
        text.contains('nikal raha') ||
        text.contains('fail raha') ||
        text.contains('phool rahi') ||
        text.contains('bahut tez') ||
        text == 'y' ||
        text == 'yeah' ||
        text == 'yep';
  }
}
