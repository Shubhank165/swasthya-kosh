"""Dashavidha Pariksha - the ten-fold Ayurvedic examination - as far as a kiosk can honestly take it.

Of the ten parameters, only some are things a patient can report about themselves. Vaya (age) and
Vikriti (the presenting disturbance) are already captured by the clinical intake, so they are not
asked twice. Prakriti, Ahara Shakti, Vyayama Shakti, Satva and Satmya are self-reportable and are
asked here as touch questions. Sara (tissue quality), Samhanana (build) and Pramana (measurements)
need a clinician's hands and instruments - a kiosk with no scale and no stadiometer cannot assess
them, so they are reported as pending rather than guessed at.

Scoring is a tally, not a model. A 1B model asked to classify constitution would produce a
confident Prakriti for any input, and a wrong Prakriti printed on a doctor's sheet is worse than an
honest "insufficient responses". The summary therefore only names a dominant dosha when the
answers actually lean one way, and says so plainly when they do not.

Nothing here diagnoses. It is intake: the vaidya reads it and decides.
"""

from __future__ import annotations

from dataclasses import dataclass

VATA, PITTA, KAPHA = "vata", "pitta", "kapha"

# Parameters a patient cannot self-report. Named explicitly so the doctor's sheet shows what is
# missing and why, instead of silently omitting three of the ten.
CLINICIAN_ASSESSED: dict[str, dict[str, str]] = {
    "sara": {
        "en": "Sara (tissue quality)",
        "hi": "सार (धातु गुणवत्ता)",
        "bn": "সার (ধাতুর গুণ)",
        "mr": "सार (धातू गुणवत्ता)",
        "te": "సార (ధాతు నాణ్యత)",
        "ta": "சார (திசு தரம்)",
        "gu": "સાર (ધાતુ ગુણવત્તા)",
        "kn": "ಸಾರ (ಧಾತು ಗುಣಮಟ್ಟ)",
        "pa": "ਸਾਰ (ਧਾਤੂ ਗੁਣਵੱਤਾ)",
    },
    "samhanana": {
        "en": "Samhanana (body build and compactness)",
        "hi": "संहनन (शरीर गठन)",
        "bn": "সংহনন (দেহগঠন)",
        "mr": "संहनन (शरीर गठन)",
        "te": "సంహనన (శరీర నిర్మాణం)",
        "ta": "சம்ஹனன (உடல் அமைப்பு)",
        "gu": "સંહનન (શરીર બાંધો)",
        "kn": "ಸಂಹನನ (ದೇಹ ರಚನೆ)",
        "pa": "ਸੰਹਨਨ (ਸਰੀਰ ਗਠਨ)",
    },
    "pramana": {
        "en": "Pramana (body measurements)",
        "hi": "प्रमाण (शरीर माप)",
        "bn": "প্রমাণ (দেহ পরিমাপ)",
        "mr": "प्रमाण (शरीर माप)",
        "te": "ప్రమాణ (శరీర కొలతలు)",
        "ta": "பிரமாண (உடல் அளவுகள்)",
        "gu": "પ્રમાણ (શરીર માપ)",
        "kn": "ಪ್ರಮಾಣ (ದೇಹ ಅಳತೆ)",
        "pa": "ਪ੍ਰਮਾਣ (ਸਰੀਰ ਮਾਪ)",
    },
}


@dataclass(frozen=True)
class Option:
    value: str
    label: dict[str, str]
    dosha: str | None = None
    # Symbol name the kiosk draws for this choice. A patient who cannot read has to be able to
    # answer from the picture alone, so the icon carries the meaning and the label confirms it.
    # Named here rather than in each client so the tablet app, the browser and the 2.8" panel
    # all show the same symbol for the same answer.
    icon: str = "circle"


@dataclass(frozen=True)
class AyurvedaQuestion:
    id: str
    parameter: str
    text: dict[str, str]
    options: tuple[Option, ...]

    def text_for(self, language: str | None) -> str:
        return self.text.get((language or "en")[:2], self.text["en"])

    def options_for(self, language: str | None) -> list[dict[str, str]]:
        code = (language or "en")[:2]
        return [
            {
                "value": option.value,
                "label": option.label.get(code, option.label["en"]),
                "icon": option.icon,
            }
            for option in self.options
        ]


QUESTIONS: tuple[AyurvedaQuestion, ...] = (
    AyurvedaQuestion(
        id="ayu_build",
        parameter="prakriti",
        text={
            "en": "How would you describe your body build?",
            "hi": "आपके शरीर की बनावट कैसी है?",
            "bn": "আপনার শরীরের গড়ন কেমন?",
            "mr": "तुमच्या शरीराची ठेवण कशी आहे?",
            "te": "మీ శరీర ఆకృతి ఎలా ఉంటుంది?",
            "ta": "உங்கள் உடல் அமைப்பு எப்படி உள்ளது?",
            "gu": "તમારા શરીરની બાંધણી કેવી છે?",
            "kn": "ನಿಮ್ಮ ದೇಹದ ರಚನೆ ಹೇಗಿದೆ?",
            "pa": "ਤੁਹਾਡੇ ਸਰੀਰ ਦੀ ਬਣਤਰ ਕਿਹੋ ਜਿਹੀ ਹੈ?",
        },
        options=(
            Option(
                "thin",
                {
                    "en": "Thin, hard to gain weight",
                    "hi": "पतला, वज़न बढ़ना मुश्किल",
                    "bn": "পাতলা, ওজন বাড়ানো কঠিন",
                    "mr": "बारीक, वजन वाढणे कठीण",
                    "te": "సన్నగా, బరువు పెరగడం కష్టం",
                    "ta": "மெலிந்த, எடை கூட்டுவது கடினம்",
                    "gu": "પાતળું, વજન વધારવું મુશ્કેલ",
                    "kn": "ತೆಳ್ಳಗೆ, ತೂಕ ಹೆಚ್ಚಿಸುವುದು ಕಷ್ಟ",
                    "pa": "ਪਤਲਾ, ਭਾਰ ਵਧਾਉਣਾ ਔਖਾ",
                },
                VATA, icon="body_thin",
            ),
            Option(
                "medium",
                {
                    "en": "Medium, well proportioned",
                    "hi": "मध्यम, संतुलित",
                    "bn": "মাঝারি, সুগঠিত",
                    "mr": "मध्यम, प्रमाणबद्ध",
                    "te": "మధ్యస్థం, సమతుల్యం",
                    "ta": "நடுத்தரம், சமச்சீர்",
                    "gu": "મધ્યમ, સપ્રમાણ",
                    "kn": "ಮಧ್ಯಮ, ಸಮತೋಲಿತ",
                    "pa": "ਦਰਮਿਆਨਾ, ਸੰਤੁਲਿਤ",
                },
                PITTA, icon="body_medium",
            ),
            Option(
                "heavy",
                {
                    "en": "Heavy, gains weight easily",
                    "hi": "भारी, वज़न जल्दी बढ़ता है",
                    "bn": "ভারী, সহজে ওজন বাড়ে",
                    "mr": "जड, वजन सहज वाढते",
                    "te": "బరువుగా, సులభంగా బరువు పెరుగుతుంది",
                    "ta": "கனமான, எளிதில் எடை கூடும்",
                    "gu": "ભારે, વજન સહેલાઈથી વધે",
                    "kn": "ಭಾರವಾದ, ಸುಲಭವಾಗಿ ತೂಕ ಹೆಚ್ಚಾಗುತ್ತದೆ",
                    "pa": "ਭਾਰਾ, ਭਾਰ ਸੌਖਾ ਵਧਦਾ ਹੈ",
                },
                KAPHA, icon="body_heavy",
            ),
        ),
    ),
    AyurvedaQuestion(
        id="ayu_skin",
        parameter="prakriti",
        text={
            "en": "How is your skin usually?",
            "hi": "आपकी त्वचा आमतौर पर कैसी रहती है?",
            "bn": "আপনার ত্বক সাধারণত কেমন থাকে?",
            "mr": "तुमची त्वचा सहसा कशी असते?",
            "te": "మీ చర్మం సాధారణంగా ఎలా ఉంటుంది?",
            "ta": "உங்கள் தோல் பொதுவாக எப்படி இருக்கும்?",
            "gu": "તમારી ત્વચા સામાન્ય રીતે કેવી હોય છે?",
            "kn": "ನಿಮ್ಮ ಚರ್ಮ ಸಾಮಾನ್ಯವಾಗಿ ಹೇಗಿರುತ್ತದೆ?",
            "pa": "ਤੁਹਾਡੀ ਚਮੜੀ ਆਮ ਤੌਰ ਤੇ ਕਿਹੋ ਜਿਹੀ ਰਹਿੰਦੀ ਹੈ?",
        },
        options=(
            Option(
                "dry",
                {
                    "en": "Dry and rough",
                    "hi": "रूखी और खुरदरी",
                    "bn": "শুষ্ক ও খসখসে",
                    "mr": "कोरडी आणि खरखरीत",
                    "te": "పొడిగా, గరుకుగా",
                    "ta": "வறண்ட மற்றும் கரடுமுரடான",
                    "gu": "સૂકી અને ખરબચડી",
                    "kn": "ಒಣ ಮತ್ತು ಒರಟು",
                    "pa": "ਖੁਸ਼ਕ ਅਤੇ ਖੁਰਦਰੀ",
                },
                VATA, icon="skin_dry",
            ),
            Option(
                "warm",
                {
                    "en": "Warm, oily, prone to rashes",
                    "hi": "गर्म, तैलीय, चकत्ते होते हैं",
                    "bn": "গরম, তৈলাক্ত, র‍্যাশ হয়",
                    "mr": "उष्ण, तेलकट, पुरळ येते",
                    "te": "వెచ్చగా, జిడ్డుగా, దద్దుర్లు వస్తాయి",
                    "ta": "சூடான, எண்ணெய்ப்பசை, தடிப்பு வரும்",
                    "gu": "ગરમ, તૈલી, ફોલ્લી થાય",
                    "kn": "ಬೆಚ್ಚಗಿನ, ಎಣ್ಣೆಯುಕ್ತ, ಗುಳ್ಳೆ ಬರುತ್ತದೆ",
                    "pa": "ਗਰਮ, ਤੇਲੀ, ਧੱਫੜ ਹੁੰਦੇ ਹਨ",
                },
                PITTA, icon="skin_warm",
            ),
            Option(
                "soft",
                {
                    "en": "Soft, cool, moist",
                    "hi": "मुलायम, ठंडी, नम",
                    "bn": "নরম, ঠান্ডা, আর্দ্র",
                    "mr": "मऊ, थंड, ओलसर",
                    "te": "మృదువుగా, చల్లగా, తేమగా",
                    "ta": "மென்மையான, குளிர்ந்த, ஈரமான",
                    "gu": "નરમ, ઠંડી, ભેજવાળી",
                    "kn": "ಮೃದು, ತಂಪು, ತೇವ",
                    "pa": "ਨਰਮ, ਠੰਢੀ, ਨਮ",
                },
                KAPHA, icon="skin_soft",
            ),
        ),
    ),
    AyurvedaQuestion(
        id="ayu_sleep",
        parameter="prakriti",
        text={
            "en": "How do you sleep?",
            "hi": "आपकी नींद कैसी है?",
            "bn": "আপনার ঘুম কেমন হয়?",
            "mr": "तुमची झोप कशी असते?",
            "te": "మీ నిద్ర ఎలా ఉంటుంది?",
            "ta": "உங்கள் தூக்கம் எப்படி இருக்கும்?",
            "gu": "તમારી ઊંઘ કેવી છે?",
            "kn": "ನಿಮ್ಮ ನಿದ್ರೆ ಹೇಗಿರುತ್ತದೆ?",
            "pa": "ਤੁਹਾਡੀ ਨੀਂਦ ਕਿਹੋ ਜਿਹੀ ਹੈ?",
        },
        options=(
            Option(
                "light",
                {
                    "en": "Light, wake often",
                    "hi": "कच्ची, बार-बार खुलती है",
                    "bn": "পাতলা, বারবার ঘুম ভাঙে",
                    "mr": "कच्ची, वारंवार जाग येते",
                    "te": "తేలికగా, తరచూ మెలకువ",
                    "ta": "லேசான, அடிக்கடி விழிப்பு",
                    "gu": "કાચી, વારંવાર ઊંઘ ઊડે",
                    "kn": "ಹಗುರ, ಪದೇ ಪದೇ ಎಚ್ಚರ",
                    "pa": "ਹਲਕੀ, ਵਾਰ ਵਾਰ ਖੁੱਲ੍ਹਦੀ ਹੈ",
                },
                VATA, icon="sleep_light",
            ),
            Option(
                "moderate",
                {
                    "en": "Moderate, wake refreshed",
                    "hi": "ठीक, तरोताज़ा उठता हूँ",
                    "bn": "মাঝারি, সতেজ হয়ে উঠি",
                    "mr": "ठीक, ताजेतवाने उठतो",
                    "te": "మధ్యస్థం, హాయిగా లేస్తాను",
                    "ta": "நடுத்தரம், புத்துணர்ச்சியுடன் எழுவேன்",
                    "gu": "મધ્યમ, તાજગીથી ઊઠું",
                    "kn": "ಮಧ್ಯಮ, ಉಲ್ಲಾಸದಿಂದ ಏಳುತ್ತೇನೆ",
                    "pa": "ਠੀਕ, ਤਾਜ਼ਾ ਉੱਠਦਾ ਹਾਂ",
                },
                PITTA, icon="sleep_moderate",
            ),
            Option(
                "deep",
                {
                    "en": "Deep and long",
                    "hi": "गहरी और लंबी",
                    "bn": "গভীর ও দীর্ঘ",
                    "mr": "गाढ आणि लांब",
                    "te": "గాఢంగా, ఎక్కువసేపు",
                    "ta": "ஆழமான, நீண்ட",
                    "gu": "ગાઢ અને લાંબી",
                    "kn": "ಗಾಢ ಮತ್ತು ದೀರ್ಘ",
                    "pa": "ਗੂੜ੍ਹੀ ਅਤੇ ਲੰਬੀ",
                },
                KAPHA, icon="sleep_deep",
            ),
        ),
    ),
    AyurvedaQuestion(
        id="ayu_weather",
        parameter="prakriti",
        text={
            "en": "Which weather troubles you most?",
            "hi": "कौन सा मौसम आपको सबसे ज़्यादा परेशान करता है?",
            "bn": "কোন আবহাওয়া আপনাকে সবচেয়ে কষ্ট দেয়?",
            "mr": "कोणते हवामान तुम्हाला सर्वात त्रास देते?",
            "te": "ఏ వాతావరణం మిమ్మల్ని ఎక్కువగా ఇబ్బంది పెడుతుంది?",
            "ta": "எந்த வானிலை உங்களை அதிகம் பாதிக்கிறது?",
            "gu": "કયું હવામાન તમને સૌથી વધુ પરેશાન કરે છે?",
            "kn": "ಯಾವ ಹವಾಮಾನ ನಿಮಗೆ ಹೆಚ್ಚು ತೊಂದರೆ ನೀಡುತ್ತದೆ?",
            "pa": "ਕਿਹੜਾ ਮੌਸਮ ਤੁਹਾਨੂੰ ਸਭ ਤੋਂ ਵੱਧ ਤੰਗ ਕਰਦਾ ਹੈ?",
        },
        options=(
            Option(
                "cold",
                {
                    "en": "Cold and windy",
                    "hi": "ठंड और हवा",
                    "bn": "ঠান্ডা ও হাওয়া",
                    "mr": "थंडी आणि वारा",
                    "te": "చలి, గాలి",
                    "ta": "குளிர் மற்றும் காற்று",
                    "gu": "ઠંડી અને પવન",
                    "kn": "ಚಳಿ ಮತ್ತು ಗಾಳಿ",
                    "pa": "ਠੰਢ ਅਤੇ ਹਵਾ",
                },
                VATA, icon="weather_cold",
            ),
            Option(
                "hot",
                {
                    "en": "Hot and humid",
                    "hi": "गर्मी और उमस",
                    "bn": "গরম ও আর্দ্র",
                    "mr": "उष्ण आणि दमट",
                    "te": "వేడి, తేమ",
                    "ta": "வெப்பம் மற்றும் ஈரப்பதம்",
                    "gu": "ગરમી અને ભેજ",
                    "kn": "ಸೆಕೆ ಮತ್ತು ತೇವ",
                    "pa": "ਗਰਮੀ ਅਤੇ ਸਿੱਲ੍ਹ",
                },
                PITTA, icon="weather_hot",
            ),
            Option(
                "damp",
                {
                    "en": "Damp and cool",
                    "hi": "नमी और ठंडक",
                    "bn": "স্যাঁতসেঁতে ও ঠান্ডা",
                    "mr": "ओलसर आणि थंड",
                    "te": "తడి, చల్లదనం",
                    "ta": "ஈரமான மற்றும் குளிர்",
                    "gu": "ભેજ અને ઠંડક",
                    "kn": "ತೇವ ಮತ್ತು ತಂಪು",
                    "pa": "ਸਿੱਲ੍ਹ ਅਤੇ ਠੰਢ",
                },
                KAPHA, icon="weather_damp",
            ),
        ),
    ),
    AyurvedaQuestion(
        id="ayu_temperament",
        parameter="satva",
        text={
            "en": "Under stress, what happens to you most often?",
            "hi": "तनाव में आपके साथ अक्सर क्या होता है?",
            "bn": "চাপের সময় আপনার সাধারণত কী হয়?",
            "mr": "तणावात तुमच्यासोबत बहुधा काय होते?",
            "te": "ఒత్తిడిలో మీకు తరచుగా ఏమి జరుగుతుంది?",
            "ta": "மன அழுத்தத்தில் உங்களுக்கு அடிக்கடி என்ன நடக்கும்?",
            "gu": "તણાવમાં તમારી સાથે મોટે ભાગે શું થાય છે?",
            "kn": "ಒತ್ತಡದಲ್ಲಿ ನಿಮಗೆ ಹೆಚ್ಚಾಗಿ ಏನಾಗುತ್ತದೆ?",
            "pa": "ਤਣਾਅ ਵਿੱਚ ਤੁਹਾਡੇ ਨਾਲ ਅਕਸਰ ਕੀ ਹੁੰਦਾ ਹੈ?",
        },
        options=(
            Option(
                "anxious",
                {
                    "en": "I become anxious or restless",
                    "hi": "घबराहट या बेचैनी होती है",
                    "bn": "উদ্বিগ্ন বা অস্থির হয়ে পড়ি",
                    "mr": "अस्वस्थ किंवा बेचैन होतो",
                    "te": "ఆందోళన లేదా అశాంతి కలుగుతుంది",
                    "ta": "பதட்டம் அல்லது அமைதியின்மை ஏற்படும்",
                    "gu": "ચિંતિત કે બેચેન થઈ જાઉં",
                    "kn": "ಆತಂಕ ಅಥವಾ ಚಡಪಡಿಕೆ ಆಗುತ್ತದೆ",
                    "pa": "ਘਬਰਾਹਟ ਜਾਂ ਬੇਚੈਨੀ ਹੁੰਦੀ ਹੈ",
                },
                VATA, icon="mood_anxious",
            ),
            Option(
                "irritable",
                {
                    "en": "I become irritable",
                    "hi": "चिड़चिड़ापन या गुस्सा आता है",
                    "bn": "খিটখিটে হয়ে যাই",
                    "mr": "चिडचिड होते",
                    "te": "చిరాకు వస్తుంది",
                    "ta": "எரிச்சல் ஏற்படும்",
                    "gu": "ચીડિયો થઈ જાઉં",
                    "kn": "ಕಿರಿಕಿರಿ ಆಗುತ್ತದೆ",
                    "pa": "ਚਿੜਚਿੜਾਪਨ ਹੁੰਦਾ ਹੈ",
                },
                PITTA, icon="mood_angry",
            ),
            Option(
                "withdrawn",
                {
                    "en": "I become quiet and withdrawn",
                    "hi": "चुप और अलग हो जाता हूँ",
                    "bn": "চুপচাপ ও গুটিয়ে যাই",
                    "mr": "शांत आणि अलिप्त होतो",
                    "te": "మౌనంగా, ఒంటరిగా ఉంటాను",
                    "ta": "அமைதியாகி விலகி இருப்பேன்",
                    "gu": "શાંત અને અલગ થઈ જાઉં",
                    "kn": "ಮೌನವಾಗಿ ದೂರ ಉಳಿಯುತ್ತೇನೆ",
                    "pa": "ਚੁੱਪ ਅਤੇ ਵੱਖਰਾ ਹੋ ਜਾਂਦਾ ਹਾਂ",
                },
                KAPHA, icon="mood_quiet",
            ),
        ),
    ),
    AyurvedaQuestion(
        id="ayu_appetite",
        parameter="ahara_shakti",
        text={
            "en": "How is your appetite and digestion?",
            "hi": "आपकी भूख और पाचन कैसा है?",
            "bn": "আপনার খিদে ও হজম কেমন?",
            "mr": "तुमची भूक आणि पचन कसे आहे?",
            "te": "మీ ఆకలి, జీర్ణక్రియ ఎలా ఉంది?",
            "ta": "உங்கள் பசி மற்றும் செரிமானம் எப்படி?",
            "gu": "તમારી ભૂખ અને પાચન કેવું છે?",
            "kn": "ನಿಮ್ಮ ಹಸಿವು ಮತ್ತು ಜೀರ್ಣ ಹೇಗಿದೆ?",
            "pa": "ਤੁਹਾਡੀ ਭੁੱਖ ਅਤੇ ਪਾਚਨ ਕਿਹੋ ਜਿਹਾ ਹੈ?",
        },
        options=(
            Option(
                "strong",
                {
                    "en": "Strong, digest easily",
                    "hi": "तेज़, पाचन अच्छा",
                    "bn": "ভালো, সহজে হজম হয়",
                    "mr": "चांगली, सहज पचते",
                    "te": "బాగుంది, సులభంగా జీర్ణం",
                    "ta": "நல்லது, எளிதில் செரிமானம்",
                    "gu": "સારી, સહેલાઈથી પચે",
                    "kn": "ಚೆನ್ನಾಗಿದೆ, ಸುಲಭವಾಗಿ ಜೀರ್ಣ",
                    "pa": "ਚੰਗੀ, ਸੌਖਾ ਪਚਦਾ ਹੈ",
                },
                icon="appetite_strong",
            ),
            Option(
                "moderate",
                {
                    "en": "Moderate",
                    "hi": "ठीक-ठाक",
                    "bn": "মাঝারি",
                    "mr": "ठीकठाक",
                    "te": "మధ్యస్థం",
                    "ta": "நடுத்தரம்",
                    "gu": "મધ્યમ",
                    "kn": "ಮಧ್ಯಮ",
                    "pa": "ਦਰਮਿਆਨੀ",
                },
                icon="appetite_moderate",
            ),
            Option(
                "irregular",
                {
                    "en": "Irregular, varies day to day",
                    "hi": "अनियमित, रोज़ बदलती है",
                    "bn": "অনিয়মিত, রোজ বদলায়",
                    "mr": "अनियमित, रोज बदलते",
                    "te": "క్రమం లేదు, రోజుకో రకం",
                    "ta": "ஒழுங்கற்றது, நாளுக்கு நாள் மாறும்",
                    "gu": "અનિયમિત, રોજ બદલાય",
                    "kn": "ಅನಿಯಮಿತ, ದಿನದಿಂದ ದಿನಕ್ಕೆ ಬದಲಾಗುತ್ತದೆ",
                    "pa": "ਅਨਿਯਮਿਤ, ਰੋਜ਼ ਬਦਲਦੀ ਹੈ",
                },
                icon="appetite_irregular",
            ),
            Option(
                "poor",
                {
                    "en": "Poor, heaviness after eating",
                    "hi": "कम, खाने के बाद भारीपन",
                    "bn": "কম, খাওয়ার পরে ভারী লাগে",
                    "mr": "कमी, जेवणानंतर जडपणा",
                    "te": "తక్కువ, తిన్న తర్వాత బరువు",
                    "ta": "குறைவு, சாப்பிட்ட பின் கனம்",
                    "gu": "ઓછી, જમ્યા પછી ભારેપણું",
                    "kn": "ಕಡಿಮೆ, ಊಟದ ನಂತರ ಭಾರ",
                    "pa": "ਘੱਟ, ਖਾਣ ਤੋਂ ਬਾਅਦ ਭਾਰਾਪਨ",
                },
                icon="appetite_poor",
            ),
        ),
    ),
    AyurvedaQuestion(
        id="ayu_exertion",
        parameter="vyayama_shakti",
        text={
            "en": "How much physical exertion can you manage?",
            "hi": "आप कितना शारीरिक परिश्रम कर सकते हैं?",
            "bn": "আপনি কতটা শারীরিক পরিশ্রম করতে পারেন?",
            "mr": "तुम्ही किती शारीरिक श्रम करू शकता?",
            "te": "మీరు ఎంత శారీరక శ్రమ చేయగలరు?",
            "ta": "எவ்வளவு உடல் உழைப்பு செய்ய முடியும்?",
            "gu": "તમે કેટલો શારીરિક શ્રમ કરી શકો છો?",
            "kn": "ನೀವು ಎಷ್ಟು ದೈಹಿಕ ಶ್ರಮ ಮಾಡಬಲ್ಲಿರಿ?",
            "pa": "ਤੁਸੀਂ ਕਿੰਨੀ ਸਰੀਰਕ ਮਿਹਨਤ ਕਰ ਸਕਦੇ ਹੋ?",
        },
        options=(
            Option(
                "high",
                {
                    "en": "Heavy work without tiring",
                    "hi": "भारी काम, थकान नहीं",
                    "bn": "ভারী কাজ, ক্লান্তি নেই",
                    "mr": "जड काम, थकवा नाही",
                    "te": "భారీ పని, అలసట లేదు",
                    "ta": "கடின வேலை, சோர்வில்லை",
                    "gu": "ભારે કામ, થાક નહીં",
                    "kn": "ಭಾರದ ಕೆಲಸ, ಆಯಾಸವಿಲ್ಲ",
                    "pa": "ਭਾਰਾ ਕੰਮ, ਥਕਾਵਟ ਨਹੀਂ",
                },
                icon="exertion_high",
            ),
            Option(
                "moderate",
                {
                    "en": "Ordinary daily work",
                    "hi": "रोज़ का सामान्य काम",
                    "bn": "রোজকার সাধারণ কাজ",
                    "mr": "रोजचे सामान्य काम",
                    "te": "రోజువారీ సాధారణ పని",
                    "ta": "தினசரி சாதாரண வேலை",
                    "gu": "રોજનું સામાન્ય કામ",
                    "kn": "ದಿನನಿತ್ಯದ ಸಾಮಾನ್ಯ ಕೆಲಸ",
                    "pa": "ਰੋਜ਼ ਦਾ ਆਮ ਕੰਮ",
                },
                icon="exertion_moderate",
            ),
            Option(
                "low",
                {
                    "en": "Tire quickly, need rest",
                    "hi": "जल्दी थकान, आराम चाहिए",
                    "bn": "তাড়াতাড়ি ক্লান্ত, বিশ্রাম দরকার",
                    "mr": "लवकर थकतो, विश्रांती लागते",
                    "te": "త్వరగా అలసట, విశ్రాంతి కావాలి",
                    "ta": "விரைவில் சோர்வு, ஓய்வு தேவை",
                    "gu": "જલદી થાક, આરામ જોઈએ",
                    "kn": "ಬೇಗ ಆಯಾಸ, ವಿಶ್ರಾಂತಿ ಬೇಕು",
                    "pa": "ਛੇਤੀ ਥਕਾਵਟ, ਆਰਾਮ ਚਾਹੀਦਾ",
                },
                icon="exertion_low",
            ),
        ),
    ),
    AyurvedaQuestion(
        id="ayu_diet",
        parameter="satmya",
        text={
            "en": "What is your usual diet?",
            "hi": "आपका सामान्य आहार क्या है?",
            "bn": "আপনার সাধারণ খাদ্যাভ্যাস কী?",
            "mr": "तुमचा नेहमीचा आहार काय आहे?",
            "te": "మీ సాధారణ ఆహారం ఏమిటి?",
            "ta": "உங்கள் வழக்கமான உணவு என்ன?",
            "gu": "તમારો સામાન્ય આહાર શું છે?",
            "kn": "ನಿಮ್ಮ ಸಾಮಾನ್ಯ ಆಹಾರ ಯಾವುದು?",
            "pa": "ਤੁਹਾਡਾ ਆਮ ਖਾਣਾ ਕੀ ਹੈ?",
        },
        options=(
            Option(
                "veg",
                {
                    "en": "Vegetarian",
                    "hi": "शाकाहारी",
                    "bn": "নিরামিষ",
                    "mr": "शाकाहारी",
                    "te": "శాకాహారం",
                    "ta": "சைவம்",
                    "gu": "શાકાહારી",
                    "kn": "ಸಸ್ಯಾಹಾರಿ",
                    "pa": "ਸ਼ਾਕਾਹਾਰੀ",
                },
                icon="diet_veg",
            ),
            Option(
                "mixed",
                {
                    "en": "Mixed",
                    "hi": "मिश्रित",
                    "bn": "মিশ্র",
                    "mr": "मिश्र",
                    "te": "మిశ్రమం",
                    "ta": "கலப்பு",
                    "gu": "મિશ્ર",
                    "kn": "ಮಿಶ್ರ",
                    "pa": "ਮਿਸ਼ਰਤ",
                },
                icon="diet_mixed",
            ),
            Option(
                "irregular",
                {
                    "en": "Irregular, often skip meals",
                    "hi": "अनियमित, भोजन छूटता है",
                    "bn": "অনিয়মিত, প্রায়ই খাবার বাদ",
                    "mr": "अनियमित, जेवण चुकते",
                    "te": "క్రమం లేదు, భోజనం తప్పుతుంది",
                    "ta": "ஒழுங்கற்றது, உணவு தவறும்",
                    "gu": "અનિયમિત, ભોજન ચૂકી જવાય",
                    "kn": "ಅನಿಯಮಿತ, ಊಟ ತಪ್ಪುತ್ತದೆ",
                    "pa": "ਅਨਿਯਮਿਤ, ਖਾਣਾ ਖੁੰਝਦਾ ਹੈ",
                },
                icon="diet_irregular",
            ),
        ),
    ),
)

BY_ID = {question.id: question for question in QUESTIONS}


def next_question(answers: dict[str, str]) -> AyurvedaQuestion | None:
    for question in QUESTIONS:
        if question.id not in answers:
            return question
    return None


def summarize(answers: dict[str, str], age_years: int | None = None) -> dict[str, object]:
    """Deterministic tally of the answers given. Never names a dosha the answers do not support."""

    tally = {VATA: 0, PITTA: 0, KAPHA: 0}
    for question_id, value in answers.items():
        question = BY_ID.get(question_id)
        if question is None:
            continue
        for option in question.options:
            if option.value == value and option.dosha:
                tally[option.dosha] += 1

    total = sum(tally.values())
    ranked = sorted(tally.items(), key=lambda item: item[1], reverse=True)
    if total < 3:
        dominant: str | None = None
        note = "Insufficient responses to indicate a constitution."
    elif ranked[0][1] == ranked[1][1]:
        # A tie is a real finding in Ayurveda (dvandvaja prakriti), not a failure to decide.
        dominant = f"{ranked[0][0]}-{ranked[1][0]}"
        note = "Dual tendency; responses did not favour one dosha."
    else:
        dominant = ranked[0][0]
        note = f"Leaning {dominant} on {ranked[0][1]} of {total} constitution responses."

    return {
        "prakriti_tendency": dominant,
        "prakriti_note": note,
        "dosha_tally": tally,
        "ahara_shakti": answers.get("ayu_appetite"),
        "vyayama_shakti": answers.get("ayu_exertion"),
        "satva": answers.get("ayu_temperament"),
        "satmya": answers.get("ayu_diet"),
        "vaya_years": age_years,
        "pending_clinician_assessment": sorted(CLINICIAN_ASSESSED),
        "answered": len(answers),
        "total_questions": len(QUESTIONS),
    }
