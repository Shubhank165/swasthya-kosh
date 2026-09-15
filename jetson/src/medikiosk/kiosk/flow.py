"""The eight-step kiosk workflow, as one state machine.

    1 language   2 ABHA   3 who is answering   4+5 describe issue and interview
    6 Ayurvedic questionnaire   7 Prakriti (once in a lifetime)   8 documents
    9 report and queue

Steps 4 and 5 are one stage here, not two: "describe the issue" is already the first question the
ClinicalStateMachine asks, and splitting it would mean two components owning the same slot. That
existing machine, the red-flag rules and the extractors are untouched - this only sequences around
them, so nothing about the clinical safety path changes shape.

Red flags short-circuit from any stage straight to EMERGENCY. That is the whole point of them: a
patient describing crushing chest pain during the Ayurvedic questionnaire must not be walked
through four more screens before anyone is told.

Each stage declares how it takes input - touch, voice, or camera - so a client (browser now, Kivy
app next) can render the right control without knowing anything about clinical logic.
"""

from __future__ import annotations

from enum import Enum

from medikiosk.kiosk import ayurveda, prakriti
from medikiosk.kiosk.provenance import Ledger, Source
from medikiosk.languages import LANGUAGES
from medikiosk.models import PatientState, RedFlagAlert, Urgency


class Stage(str, Enum):
    LANGUAGE = "language"
    ABHA = "abha"
    WHO = "who"
    INTERVIEW = "interview"
    AYURVEDA = "ayurveda"
    PRAKRITI = "prakriti"
    DOCUMENTS = "documents"
    REPORT = "report"
    EMERGENCY = "emergency"


ORDER = (
    Stage.LANGUAGE,
    Stage.ABHA,
    Stage.WHO,
    Stage.INTERVIEW,
    Stage.AYURVEDA,
    Stage.PRAKRITI,
    Stage.DOCUMENTS,
    Stage.REPORT,
)

# Screen text for the stages that are not driven by the clinical question table.
#
# These are navigation and status lines - "Skip", "Scan", "Show your ABHA card" - not clinical
# wording, which is why they are translated here while the Prakriti questionnaire still is not.
# A patient who cannot read English could not move through the kiosk at all without them: before
# this, seven of the nine languages fell back to English for every one of these lines, and the
# pre-render step then spoke them in the English voice, so 87 of the 112 prompts a Tamil patient
# heard were English.
#
# The seven non-Hindi translations have NOT been checked by a native speaker. They are plain
# navigation phrases rather than diagnosis, so the risk is a stilted sentence rather than a wrong
# clinical claim - but `emergency` is read aloud when staff are being called, and that one in
# particular deserves a first-language reader before this goes in front of patients.
SCREEN_TEXT: dict[str, dict[str, str]] = {
    "language": {
        "en": "Choose your language",
        "hi": "अपनी भाषा चुनें",
        "bn": "আপনার ভাষা বেছে নিন",
        "mr": "तुमची भाषा निवडा",
        "te": "మీ భాషను ఎంచుకోండి",
        "ta": "உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்",
        "gu": "તમારી ભાષા પસંદ કરો",
        "kn": "ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ",
        "pa": "ਆਪਣੀ ਭਾਸ਼ਾ ਚੁਣੋ",
    },
    "abha": {
        "en": "Show your ABHA card to the camera, or enter your ABHA number. You may also skip.",
        "hi": "अपना आभा कार्ड कैमरे को दिखाएँ, या आभा नंबर डालें। आप छोड़ भी सकते हैं।",
        "bn": "আপনার আভা কার্ড ক্যামেরায় দেখান, বা আভা নম্বর লিখুন। আপনি এড়িয়েও যেতে পারেন।",
        "mr": "तुमचे आभा कार्ड कॅमेऱ्याला दाखवा, किंवा आभा क्रमांक टाका. तुम्ही वगळूही शकता.",
        "te": "మీ ఆభా కార్డును కెమెరాకు చూపండి, లేదా ఆభా నంబర్ నమోదు చేయండి. మీరు దాటవేయవచ్చు.",
        "ta": "உங்கள் ஆபா அட்டையை கேமராவில் காட்டுங்கள், அல்லது ஆபா எண்ணை உள்ளிடுங்கள். தவிர்க்கவும் செய்யலாம்.",
        "gu": "તમારું આભા કાર્ડ કૅમેરાને બતાવો, અથવા આભા નંબર દાખલ કરો. તમે છોડી પણ શકો છો.",
        "kn": "ನಿಮ್ಮ ಆಭಾ ಕಾರ್ಡ್ ಅನ್ನು ಕ್ಯಾಮೆರಾಗೆ ತೋರಿಸಿ, ಅಥವಾ ಆಭಾ ಸಂಖ್ಯೆಯನ್ನು ನಮೂದಿಸಿ. ನೀವು ಬಿಟ್ಟುಬಿಡಬಹುದು.",
        "pa": "ਆਪਣਾ ਆਭਾ ਕਾਰਡ ਕੈਮਰੇ ਨੂੰ ਦਿਖਾਓ, ਜਾਂ ਆਭਾ ਨੰਬਰ ਭਰੋ। ਤੁਸੀਂ ਛੱਡ ਵੀ ਸਕਦੇ ਹੋ।",
    },
    "abha_found": {
        "en": "Welcome back. Your previous visits have been loaded.",
        "hi": "आपका फिर से स्वागत है। आपकी पिछली विज़िट मिल गई हैं।",
        "bn": "আবার স্বাগতম। আপনার আগের ভিজিট পাওয়া গেছে।",
        "mr": "पुन्हा स्वागत आहे. तुमच्या मागील भेटी मिळाल्या आहेत.",
        "te": "మళ్ళీ స్వాగతం. మీ మునుపటి సందర్శనలు లభించాయి.",
        "ta": "மீண்டும் வரவேற்கிறோம். உங்கள் முந்தைய வருகைகள் கிடைத்தன.",
        "gu": "ફરી સ્વાગત છે. તમારી અગાઉની મુલાકાતો મળી ગઈ છે.",
        "kn": "ಮತ್ತೆ ಸ್ವಾಗತ. ನಿಮ್ಮ ಹಿಂದಿನ ಭೇಟಿಗಳು ಸಿಕ್ಕಿವೆ.",
        "pa": "ਫਿਰ ਤੋਂ ਜੀ ਆਇਆਂ ਨੂੰ। ਤੁਹਾਡੀਆਂ ਪਿਛਲੀਆਂ ਮੁਲਾਕਾਤਾਂ ਮਿਲ ਗਈਆਂ ਹਨ।",
    },
    "who": {
        "en": "Are you the patient, or answering for someone else?",
        "hi": "क्या आप स्वयं रोगी हैं, या किसी और की ओर से उत्तर दे रहे हैं?",
        "bn": "আপনি কি নিজেই রোগী, নাকি অন্য কারও হয়ে উত্তর দিচ্ছেন?",
        "mr": "तुम्ही स्वतः रुग्ण आहात, की दुसऱ्या कोणासाठी उत्तर देत आहात?",
        "te": "మీరు స్వయంగా రోగినా, లేదా వేరొకరి తరపున సమాధానం ఇస్తున్నారా?",
        "ta": "நீங்கள் நோயாளியா, அல்லது வேறு ஒருவருக்காக பதிலளிக்கிறீர்களா?",
        "gu": "તમે પોતે દર્દી છો, કે બીજા કોઈ વતી જવાબ આપી રહ્યા છો?",
        "kn": "ನೀವು ಸ್ವತಃ ರೋಗಿಯೇ, ಅಥವಾ ಬೇರೊಬ್ಬರ ಪರವಾಗಿ ಉತ್ತರಿಸುತ್ತಿದ್ದೀರಾ?",
        "pa": "ਕੀ ਤੁਸੀਂ ਖੁਦ ਮਰੀਜ਼ ਹੋ, ਜਾਂ ਕਿਸੇ ਹੋਰ ਵੱਲੋਂ ਜਵਾਬ ਦੇ ਰਹੇ ਹੋ?",
    },
    "who_self": {
        "en": "I am the patient",
        "hi": "मैं स्वयं रोगी हूँ",
        "bn": "আমিই রোগী",
        "mr": "मी स्वतः रुग्ण आहे",
        "te": "నేనే రోగిని",
        "ta": "நானே நோயாளி",
        "gu": "હું જ દર્દી છું",
        "kn": "ನಾನೇ ರೋಗಿ",
        "pa": "ਮੈਂ ਹੀ ਮਰੀਜ਼ ਹਾਂ",
    },
    "who_other": {
        "en": "I am answering for someone else",
        "hi": "मैं किसी और की ओर से बोल रहा हूँ",
        "bn": "আমি অন্য কারও হয়ে উত্তর দিচ্ছি",
        "mr": "मी दुसऱ्या कोणासाठी उत्तर देत आहे",
        "te": "నేను వేరొకరి తరపున సమాధానం ఇస్తున్నాను",
        "ta": "நான் வேறு ஒருவருக்காக பதிலளிக்கிறேன்",
        "gu": "હું બીજા કોઈ વતી જવાબ આપી રહ્યો છું",
        "kn": "ನಾನು ಬೇರೊಬ್ಬರ ಪರವಾಗಿ ಉತ್ತರಿಸುತ್ತಿದ್ದೇನೆ",
        "pa": "ਮੈਂ ਕਿਸੇ ਹੋਰ ਵੱਲੋਂ ਜਵਾਬ ਦੇ ਰਿਹਾ ਹਾਂ",
    },
    "ayurveda_intro": {
        "en": "A few questions about your constitution, for the Ayurveda doctor.",
        "hi": "आयुर्वेद चिकित्सक के लिए आपकी प्रकृति से जुड़े कुछ प्रश्न।",
        "bn": "আয়ুর্বেদ চিকিৎসকের জন্য আপনার প্রকৃতি সম্পর্কে কয়েকটি প্রশ্ন।",
        "mr": "आयुर्वेद डॉक्टरांसाठी तुमच्या प्रकृतीबद्दल काही प्रश्न.",
        "te": "ఆయుర్వేద వైద్యుని కోసం మీ ప్రకృతి గురించి కొన్ని ప్రశ్నలు.",
        "ta": "ஆயுர்வேத மருத்துவருக்காக உங்கள் பிரகிருதி பற்றிய சில கேள்விகள்.",
        "gu": "આયુર્વેદ ડૉક્ટર માટે તમારી પ્રકૃતિ વિશે થોડા પ્રશ્નો.",
        "kn": "ಆಯುರ್ವೇದ ವೈದ್ಯರಿಗಾಗಿ ನಿಮ್ಮ ಪ್ರಕೃತಿಯ ಬಗ್ಗೆ ಕೆಲವು ಪ್ರಶ್ನೆಗಳು.",
        "pa": "ਆਯੁਰਵੇਦ ਡਾਕਟਰ ਲਈ ਤੁਹਾਡੀ ਪ੍ਰਕ੍ਰਿਤੀ ਬਾਰੇ ਕੁਝ ਸਵਾਲ।",
    },
    "documents": {
        "en": "Place any prescription or report under the camera, then press Scan. Or skip.",
        "hi": "कोई पर्चा या रिपोर्ट कैमरे के नीचे रखें, फिर स्कैन दबाएँ। या छोड़ दें।",
        "bn": "কোনো প্রেসক্রিপশন বা রিপোর্ট ক্যামেরার নিচে রাখুন, তারপর স্ক্যান চাপুন। বা এড়িয়ে যান।",
        "mr": "कोणतीही चिठ्ठी किंवा अहवाल कॅमेऱ्याखाली ठेवा, मग स्कॅन दाबा. किंवा वगळा.",
        "te": "ఏదైనా చీటీ లేదా రిపోర్టును కెమెరా కింద ఉంచి, స్కాన్ నొక్కండి. లేదా దాటవేయండి.",
        "ta": "மருந்துச் சீட்டு அல்லது அறிக்கையை கேமராவின் கீழ் வைத்து, ஸ்கேன் அழுத்தவும். அல்லது தவிர்க்கவும்.",
        "gu": "કોઈ પણ ચિઠ્ઠી કે રિપોર્ટ કૅમેરા નીચે મૂકો, પછી સ્કૅન દબાવો. અથવા છોડી દો.",
        "kn": "ಯಾವುದೇ ಚೀಟಿ ಅಥವಾ ವರದಿಯನ್ನು ಕ್ಯಾಮೆರಾದ ಕೆಳಗೆ ಇಟ್ಟು, ಸ್ಕ್ಯಾನ್ ಒತ್ತಿ. ಅಥವಾ ಬಿಟ್ಟುಬಿಡಿ.",
        "pa": "ਕੋਈ ਵੀ ਪਰਚੀ ਜਾਂ ਰਿਪੋਰਟ ਕੈਮਰੇ ਹੇਠਾਂ ਰੱਖੋ, ਫਿਰ ਸਕੈਨ ਦਬਾਓ। ਜਾਂ ਛੱਡ ਦਿਓ।",
    },
    "report": {
        "en": "Thank you. Your details have been sent to the doctor.",
        "hi": "धन्यवाद। आपका विवरण डॉक्टर को भेज दिया गया है।",
        "bn": "ধন্যবাদ। আপনার তথ্য ডাক্তারের কাছে পাঠানো হয়েছে।",
        "mr": "धन्यवाद. तुमची माहिती डॉक्टरांना पाठवली आहे.",
        "te": "ధన్యవాదాలు. మీ వివరాలు వైద్యునికి పంపబడ్డాయి.",
        "ta": "நன்றி. உங்கள் விவரங்கள் மருத்துவருக்கு அனுப்பப்பட்டன.",
        "gu": "આભાર. તમારી વિગતો ડૉક્ટરને મોકલવામાં આવી છે.",
        "kn": "ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ಮಾಹಿತಿ ವೈದ್ಯರಿಗೆ ಕಳುಹಿಸಲಾಗಿದೆ.",
        "pa": "ਧੰਨਵਾਦ। ਤੁਹਾਡੀ ਜਾਣਕਾਰੀ ਡਾਕਟਰ ਨੂੰ ਭੇਜ ਦਿੱਤੀ ਗਈ ਹੈ।",
    },
    "emergency": {
        "en": "What you described needs immediate attention. Please wait, staff are being called.",
        "hi": "आपने जो बताया उसके लिए तुरंत जाँच ज़रूरी है। कृपया रुकें, स्टाफ़ को बुलाया जा रहा है।",
        "bn": "আপনি যা বললেন তার জন্য এখনই চিকিৎসা দরকার। অনুগ্রহ করে অপেক্ষা করুন, কর্মীদের ডাকা হচ্ছে।",
        "mr": "तुम्ही सांगितलेल्यासाठी तातडीने तपासणी आवश्यक आहे. कृपया थांबा, कर्मचाऱ्यांना बोलावले जात आहे.",
        "te": "మీరు చెప్పినదానికి వెంటనే వైద్యం అవసరం. దయచేసి వేచి ఉండండి, సిబ్బందిని పిలుస్తున్నాము.",
        "ta": "நீங்கள் கூறியதற்கு உடனடி கவனிப்பு தேவை. தயவுசெய்து காத்திருங்கள், ஊழியர்கள் அழைக்கப்படுகிறார்கள்.",
        "gu": "તમે જે કહ્યું તેના માટે તાત્કાલિક તપાસ જરૂરી છે. કૃપા કરીને રાહ જુઓ, સ્ટાફને બોલાવવામાં આવી રહ્યો છે.",
        "kn": "ನೀವು ಹೇಳಿದ್ದಕ್ಕೆ ತಕ್ಷಣ ಚಿಕಿತ್ಸೆ ಅಗತ್ಯ. ದಯವಿಟ್ಟು ಕಾಯಿರಿ, ಸಿಬ್ಬಂದಿಯನ್ನು ಕರೆಯಲಾಗುತ್ತಿದೆ.",
        "pa": "ਤੁਸੀਂ ਜੋ ਦੱਸਿਆ ਉਸ ਲਈ ਤੁਰੰਤ ਜਾਂਚ ਜ਼ਰੂਰੀ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਉਡੀਕੋ, ਸਟਾਫ਼ ਨੂੰ ਬੁਲਾਇਆ ਜਾ ਰਿਹਾ ਹੈ।",
    },
    "idle": {
        "en": "MediKiosk is ready. Touch the screen to begin.",
        "hi": "मेडिकिओस्क तैयार है। शुरू करने के लिए स्क्रीन को छुएँ।",
        "bn": "মেডিকিওস্ক প্রস্তুত। শুরু করতে স্ক্রিন স্পর্শ করুন।",
        "mr": "मेडिकिओस्क तयार आहे. सुरू करण्यासाठी स्क्रीनला स्पर्श करा.",
        "te": "మెడికియోస్క్ సిద్ధంగా ఉంది. ప్రారంభించడానికి స్క్రీన్‌ను తాకండి.",
        "ta": "மெடிகியோஸ்க் தயாராக உள்ளது. தொடங்க திரையைத் தொடவும்.",
        "gu": "મેડિકિઓસ્ક તૈયાર છે. શરૂ કરવા સ્ક્રીનને સ્પર્શ કરો.",
        "kn": "ಮೆಡಿಕಿಯೋಸ್ಕ್ ಸಿದ್ಧವಾಗಿದೆ. ಪ್ರಾರಂಭಿಸಲು ಪರದೆಯನ್ನು ಸ್ಪರ್ಶಿಸಿ.",
        "pa": "ਮੈਡੀਕਿਓਸਕ ਤਿਆਰ ਹੈ। ਸ਼ੁਰੂ ਕਰਨ ਲਈ ਸਕਰੀਨ ਨੂੰ ਛੂਹੋ।",
    },
    "prakriti_ask": {
        "en": "Have you filled the Ayush Prakriti questionnaire before, at any clinic?",
        "hi": "क्या आपने पहले कभी, किसी भी चिकित्सालय में, आयुष प्रकृति प्रश्नावली भरी है?",
        "bn": "আপনি কি আগে কখনও, কোনো চিকিৎসাকেন্দ্রে, আয়ুষ প্রকৃতি প্রশ্নমালা পূরণ করেছেন?",
        "mr": "तुम्ही याआधी कधी, कोणत्याही रुग्णालयात, आयुष प्रकृती प्रश्नावली भरली आहे का?",
        "te": "మీరు ఇంతకు ముందు ఎప్పుడైనా, ఏదైనా ఆసుపత్రిలో, ఆయుష్ ప్రకృతి ప్రశ్నావళిని పూరించారా?",
        "ta": "நீங்கள் இதற்கு முன், ஏதேனும் மருத்துவமனையில், ஆயுஷ் பிரகிருதி வினாத்தாளை நிரப்பியுள்ளீர்களா?",
        "gu": "શું તમે પહેલાં ક્યારેય, કોઈ પણ દવાખાનામાં, આયુષ પ્રકૃતિ પ્રશ્નાવલી ભરી છે?",
        "kn": "ನೀವು ಈ ಹಿಂದೆ ಎಂದಾದರೂ, ಯಾವುದೇ ಆಸ್ಪತ್ರೆಯಲ್ಲಿ, ಆಯುಷ್ ಪ್ರಕೃತಿ ಪ್ರಶ್ನಾವಳಿಯನ್ನು ಭರ್ತಿ ಮಾಡಿದ್ದೀರಾ?",
        "pa": "ਕੀ ਤੁਸੀਂ ਪਹਿਲਾਂ ਕਦੇ, ਕਿਸੇ ਵੀ ਹਸਪਤਾਲ ਵਿੱਚ, ਆਯੁਸ਼ ਪ੍ਰਕ੍ਰਿਤੀ ਪ੍ਰਸ਼ਨਾਵਲੀ ਭਰੀ ਹੈ?",
    },
    "prakriti_yes": {
        "en": "Yes, I have filled it",
        "hi": "हाँ, मैंने भरी है",
        "bn": "হ্যাঁ, আমি পূরণ করেছি",
        "mr": "होय, मी भरली आहे",
        "te": "అవును, నేను పూరించాను",
        "ta": "ஆம், நான் நிரப்பியுள்ளேன்",
        "gu": "હા, મેં ભરી છે",
        "kn": "ಹೌದು, ನಾನು ಭರ್ತಿ ಮಾಡಿದ್ದೇನೆ",
        "pa": "ਹਾਂ, ਮੈਂ ਭਰੀ ਹੈ",
    },
    "prakriti_no": {
        "en": "No, or I am not sure",
        "hi": "नहीं, या मुझे याद नहीं",
        "bn": "না, বা আমার মনে নেই",
        "mr": "नाही, किंवा मला आठवत नाही",
        "te": "లేదు, లేదా నాకు గుర్తు లేదు",
        "ta": "இல்லை, அல்லது எனக்கு நினைவில்லை",
        "gu": "ના, અથવા મને યાદ નથી",
        "kn": "ಇಲ್ಲ, ಅಥವಾ ನನಗೆ ನೆನಪಿಲ್ಲ",
        "pa": "ਨਹੀਂ, ਜਾਂ ਮੈਨੂੰ ਯਾਦ ਨਹੀਂ",
    },
    "prakriti_intro": {
        "en": "These questions are about your natural constitution. They are asked only once - "
        "your answers are kept for every future visit.",
        "hi": "ये प्रश्न आपकी प्रकृति के बारे में हैं। ये केवल एक बार पूछे जाते हैं - "
        "आपके उत्तर आगे की हर विज़िट के लिए सुरक्षित रखे जाते हैं।",
        "bn": "এই প্রশ্নগুলি আপনার সহজাত প্রকৃতি সম্পর্কে। এগুলি একবারই জিজ্ঞাসা করা হয় - "
        "আপনার উত্তর ভবিষ্যতের প্রতিটি ভিজিটের জন্য রাখা হয়।",
        "mr": "हे प्रश्न तुमच्या नैसर्गिक प्रकृतीबद्दल आहेत. ते फक्त एकदाच विचारले जातात - "
        "तुमची उत्तरे पुढील प्रत्येक भेटीसाठी जपून ठेवली जातात.",
        "te": "ఈ ప్రశ్నలు మీ సహజ ప్రకృతి గురించి. ఇవి ఒకసారి మాత్రమే అడగబడతాయి - "
        "మీ సమాధానాలు భవిష్యత్ సందర్శనలన్నింటికీ భద్రపరచబడతాయి.",
        "ta": "இந்தக் கேள்விகள் உங்கள் இயற்கையான பிரகிருதி பற்றியவை. இவை ஒருமுறை மட்டுமே கேட்கப்படும் - "
        "உங்கள் பதில்கள் எதிர்கால வருகைகள் அனைத்திற்கும் சேமிக்கப்படும்.",
        "gu": "આ પ્રશ્નો તમારી કુદરતી પ્રકૃતિ વિશે છે. તે ફક્ત એક જ વાર પૂછવામાં આવે છે - "
        "તમારા જવાબો ભવિષ્યની દરેક મુલાકાત માટે રાખવામાં આવે છે.",
        "kn": "ಈ ಪ್ರಶ್ನೆಗಳು ನಿಮ್ಮ ಸಹಜ ಪ್ರಕೃತಿಯ ಬಗ್ಗೆ. ಇವು ಒಮ್ಮೆ ಮಾತ್ರ ಕೇಳಲಾಗುತ್ತವೆ - "
        "ನಿಮ್ಮ ಉತ್ತರಗಳು ಮುಂದಿನ ಪ್ರತಿ ಭೇಟಿಗೂ ಉಳಿಸಲಾಗುತ್ತವೆ.",
        "pa": "ਇਹ ਸਵਾਲ ਤੁਹਾਡੀ ਕੁਦਰਤੀ ਪ੍ਰਕ੍ਰਿਤੀ ਬਾਰੇ ਹਨ। ਇਹ ਸਿਰਫ਼ ਇੱਕ ਵਾਰ ਪੁੱਛੇ ਜਾਂਦੇ ਹਨ - "
        "ਤੁਹਾਡੇ ਜਵਾਬ ਅੱਗੇ ਦੀ ਹਰ ਮੁਲਾਕਾਤ ਲਈ ਰੱਖੇ ਜਾਂਦੇ ਹਨ।",
    },
    "prakriti_known": {
        "en": "Your constitution is already on record. These questions will not be asked again.",
        "hi": "आपकी प्रकृति पहले से दर्ज है। ये प्रश्न दोबारा नहीं पूछे जाएँगे।",
        "bn": "আপনার প্রকৃতি আগে থেকেই নথিভুক্ত আছে। এই প্রশ্নগুলি আর জিজ্ঞাসা করা হবে না।",
        "mr": "तुमची प्रकृती आधीच नोंदवलेली आहे. हे प्रश्न पुन्हा विचारले जाणार नाहीत.",
        "te": "మీ ప్రకృతి ఇప్పటికే నమోదైంది. ఈ ప్రశ్నలు మళ్ళీ అడగబడవు.",
        "ta": "உங்கள் பிரகிருதி ஏற்கனவே பதிவு செய்யப்பட்டுள்ளது. இந்தக் கேள்விகள் மீண்டும் கேட்கப்படாது.",
        "gu": "તમારી પ્રકૃતિ પહેલેથી નોંધાયેલી છે. આ પ્રશ્નો ફરી પૂછવામાં આવશે નહીં.",
        "kn": "ನಿಮ್ಮ ಪ್ರಕೃತಿ ಈಗಾಗಲೇ ದಾಖಲಾಗಿದೆ. ಈ ಪ್ರಶ್ನೆಗಳನ್ನು ಮತ್ತೆ ಕೇಳಲಾಗುವುದಿಲ್ಲ.",
        "pa": "ਤੁਹਾਡੀ ਪ੍ਰਕ੍ਰਿਤੀ ਪਹਿਲਾਂ ਹੀ ਦਰਜ ਹੈ। ਇਹ ਸਵਾਲ ਦੁਬਾਰਾ ਨਹੀਂ ਪੁੱਛੇ ਜਾਣਗੇ।",
    },
    "skip": {
        "en": "Skip", "hi": "छोड़ें", "bn": "এড়িয়ে যান", "mr": "वगळा", "te": "దాటవేయండి",
        "ta": "தவிர்", "gu": "છોડો", "kn": "ಬಿಟ್ಟುಬಿಡಿ", "pa": "ਛੱਡੋ",
    },
    "scan": {
        "en": "Scan", "hi": "स्कैन करें", "bn": "স্ক্যান করুন", "mr": "स्कॅन करा",
        "te": "స్కాన్ చేయండి", "ta": "ஸ்கேன் செய்", "gu": "સ્કૅન કરો",
        "kn": "ಸ್ಕ್ಯಾನ್ ಮಾಡಿ", "pa": "ਸਕੈਨ ਕਰੋ",
    },
    "done": {
        "en": "Done", "hi": "हो गया", "bn": "হয়ে গেছে", "mr": "झाले", "te": "పూర్తయింది",
        "ta": "முடிந்தது", "gu": "થઈ ગયું", "kn": "ಆಯಿತು", "pa": "ਹੋ ਗਿਆ",
    },
}


def text(key: str, language: str | None) -> str:
    entry = SCREEN_TEXT[key]
    return entry.get((language or "en")[:2], entry["en"])


class KioskFlow:
    """Sequences the nine steps. Owns no clinical logic - it only decides which stage is current."""

    def __init__(self, ayush_track: bool = True, prefers_ayush: bool = False) -> None:
        self.stage = Stage.LANGUAGE
        self.language: str | None = None
        self.abha_number: str | None = None
        self.past_visits: list[dict] = []
        self.on_behalf_of: str | None = None
        self.ayurveda_answers: dict[str, str] = {}
        # Prakriti is fixed for life, so it is asked once and then read back. `prakriti_record`
        # holds either what a previous visit stored or what this visit just collected;
        # `prakriti_previously_filled` is the patient's own answer to whether they have done it
        # before, which is the only signal available when they have no ABHA to look up.
        self.prakriti_answers: dict[str, str] = {}
        self.prakriti_record: dict | None = None
        self.prakriti_previously_filled: bool | None = None
        self.documents: list[dict] = []
        # ayush_track runs the Dashavidha questionnaire; prefers_ayush is the patient asking to be
        # seen by a vaidya. The first must not imply the second - see report.route.
        self.ayush_track = ayush_track
        self.prefers_ayush = prefers_ayush
        # Every value the encounter learns, with where it came from. Written as facts arrive
        # rather than reconstructed at the end, because the source is only knowable at the
        # moment of capture.
        self.ledger = Ledger()
        self.report: dict | None = None

    # ------------------------------------------------------------------ stage transitions

    def advance(self) -> Stage:
        """Move to the next stage in order. EMERGENCY and REPORT are terminal."""

        if self.stage in (Stage.EMERGENCY, Stage.REPORT):
            return self.stage
        position = ORDER.index(self.stage)
        self.stage = ORDER[position + 1]
        if self.stage is Stage.AYURVEDA and not self.ayush_track:
            self.stage = Stage.PRAKRITI
        if self.stage is Stage.PRAKRITI and not self.needs_prakriti:
            self.stage = Stage.DOCUMENTS
        return self.stage

    def back(self) -> Stage:
        """Step back one stage. A patient who mistaps a language must not be stuck with it."""

        if self.stage in (Stage.EMERGENCY, Stage.LANGUAGE):
            return self.stage
        position = ORDER.index(self.stage)
        target = ORDER[position - 1]
        if target is Stage.PRAKRITI and not self.needs_prakriti:
            target = ORDER[position - 2]
            position -= 1
        if target is Stage.AYURVEDA and not self.ayush_track:
            target = ORDER[position - 2]
        self.stage = target
        # Clear what the stage being re-entered is about to ask for again, so going back actually
        # undoes the answer instead of skipping straight past it.
        if target is Stage.ABHA:
            self.abha_number, self.past_visits = None, []
        elif target is Stage.WHO:
            self.on_behalf_of = None
        elif target is Stage.AYURVEDA and self.ayurveda_answers:
            self.ayurveda_answers.pop(list(self.ayurveda_answers)[-1], None)
        elif target is Stage.PRAKRITI and self.prakriti_answers:
            self.prakriti_answers.pop(list(self.prakriti_answers)[-1], None)
        return self.stage

    def raise_emergency(self) -> Stage:
        """Any stage can be cut short by a red flag; nothing resumes after this."""

        self.stage = Stage.EMERGENCY
        return self.stage

    def check_red_flags(self, red_flags: list[RedFlagAlert]) -> bool:
        if any(flag.urgency is Urgency.EMERGENCY for flag in red_flags):
            self.raise_emergency()
            return True
        return False

    # ------------------------------------------------------------------ stage payloads

    def screen(self, state: PatientState) -> dict:
        """What the client should show now, and what input it should accept."""

        if self.stage is Stage.LANGUAGE:
            return {
                "stage": self.stage.value,
                "input": "touch",
                "headline": text("language", self.language),
                # Each language is written in its own script, which is the icon: a patient who
                # cannot read English still recognises their own writing.
                "options": [
                    {"value": code, "label": LANGUAGES[code].native_name, "icon": f"lang_{code}"}
                    for code in sorted(LANGUAGES)
                ],
            }

        if self.stage is Stage.ABHA:
            return {
                "stage": self.stage.value,
                "input": "camera_or_text",
                "headline": text("abha", self.language),
                "skip_label": text("skip", self.language),
            }

        if self.stage is Stage.WHO:
            return {
                "stage": self.stage.value,
                "input": "touch",
                "headline": text("who", self.language),
                "options": [
                    {"value": "self", "label": text("who_self", self.language), "icon": "person_one"},
                    {"value": "other", "label": text("who_other", self.language),
                     "icon": "person_two"},
                ],
            }

        if self.stage is Stage.INTERVIEW:
            # The clinical question itself comes from ClinicalSession, which already owns wording,
            # ordering and language. Duplicating it here would create a second source of truth.
            return {"stage": self.stage.value, "input": "voice"}

        if self.stage is Stage.AYURVEDA:
            question = ayurveda.next_question(self.ayurveda_answers)
            if question is None:
                return {"stage": self.stage.value, "input": "touch", "complete": True}
            return {
                "stage": self.stage.value,
                "input": "touch",
                "question_id": question.id,
                "parameter": question.parameter,
                "headline": question.text_for(self.language),
                "options": question.options_for(self.language),
                "progress": [len(self.ayurveda_answers) + 1, len(ayurveda.QUESTIONS)],
            }

        if self.stage is Stage.PRAKRITI:
            # Three states: never asked whether they have filled it, told us they have not (so we
            # ask the questions), and finished. A patient who says they have filled it before is
            # believed - the record is somewhere the kiosk cannot reach, and making them answer
            # 46 questions to prove otherwise is worse than a vaidya asking them.
            if self.prakriti_previously_filled is None:
                return {
                    "stage": self.stage.value,
                    "input": "touch",
                    "gate": True,
                    "headline": text("prakriti_ask", self.language),
                    "options": [
                        {"value": "yes", "label": text("prakriti_yes", self.language),
                         "icon": "check"},
                        {"value": "no", "label": text("prakriti_no", self.language),
                         "icon": "cross"},
                    ],
                }
            item = prakriti.next_item(self.prakriti_answers)
            if item is None:
                return {"stage": self.stage.value, "input": "touch", "complete": True}
            return {
                "stage": self.stage.value,
                "input": "touch",
                "question_id": item.id,
                "parameter": item.section,
                "intro": text("prakriti_intro", self.language),
                "headline": item.text_for(self.language),
                "options": item.options_for(self.language),
                "progress": [len(self.prakriti_answers) + 1, len(prakriti.ITEMS)],
            }

        if self.stage is Stage.DOCUMENTS:
            return {
                "stage": self.stage.value,
                "input": "camera",
                "headline": text("documents", self.language),
                "scan_label": text("scan", self.language),
                "skip_label": text("skip", self.language),
                "scanned": len(self.documents),
            }

        if self.stage is Stage.EMERGENCY:
            return {
                "stage": self.stage.value,
                "input": "none",
                "headline": text("emergency", self.language),
                "alert": True,
            }

        return {
            "stage": self.stage.value,
            "input": "none",
            "headline": text("report", self.language),
            "report": self.report,
        }

    # ------------------------------------------------------------------ stage inputs

    def choose_language(self, code: str) -> None:
        if code not in LANGUAGES:
            raise ValueError(f"unknown language: {code}")
        self.language = code
        self.advance()

    def set_abha(self, number: str | None, history: list[dict] | None = None) -> None:
        """Record the scanned or typed ABHA number. None means the patient skipped."""

        self.abha_number = number
        self.past_visits = history or []
        for visit in self.past_visits:
            if visit.get("complaint"):
                self.ledger.record(
                    "previous_complaint",
                    visit["complaint"],
                    Source.ABHA,
                    evidence=f"visit recorded {visit.get('recorded_at', 'previously')}",
                )
        self.advance()

    def set_who(self, answer: str) -> None:
        self.on_behalf_of = None if answer == "self" else "other"
        self.advance()

    @property
    def spoken_source(self) -> Source:
        """A relative answering for a patient is reporting second-hand, and the sheet says so."""

        return (
            Source.REPRESENTATIVE_REPORTED
            if self.on_behalf_of
            else Source.PATIENT_REPORTED
        )

    def answer_ayurveda(self, question_id: str, value: str) -> bool:
        """Record one questionnaire answer. Returns True when the questionnaire is finished."""

        question = ayurveda.BY_ID.get(question_id)
        if question is None:
            raise ValueError(f"unknown ayurveda question: {question_id}")
        if value not in {option.value for option in question.options}:
            raise ValueError(f"unknown option {value!r} for {question_id}")
        self.ayurveda_answers[question_id] = value
        self.ledger.record(
            f"dashavidha.{question.parameter}",
            value,
            Source.QUESTIONNAIRE,
            evidence=question.text_for(self.language),
        )
        if ayurveda.next_question(self.ayurveda_answers) is None:
            self.advance()
            return True
        return False

    @property
    def needs_prakriti(self) -> bool:
        """Whether this patient still has to answer the Prakriti questionnaire.

        A record loaded from a previous visit settles it, and so does the patient saying they have
        filled it before. Otherwise it is asked - which is what makes it mandatory for anyone who
        has not done it.
        """

        if self.prakriti_record is not None:
            return False
        return self.prakriti_previously_filled is not True

    def load_prakriti(self, record: dict | None) -> None:
        """Attach the Prakriti stored for this patient's ABHA, if a previous visit recorded one."""

        if not record:
            return
        self.prakriti_record = record
        self.prakriti_previously_filled = True
        self.ledger.record(
            "prakriti",
            str(record.get("prakriti") or "recorded"),
            Source.ABHA,
            evidence=f"recorded {record.get('recorded_at', 'previously')}",
        )

    def answer_prakriti_gate(self, answer: str) -> bool:
        """Record whether the patient has filled the questionnaire before.

        Returns True when the stage is done (they have), False when the questions now follow.
        """

        if answer not in {"yes", "no"}:
            raise ValueError(f"unknown prakriti gate answer: {answer!r}")
        self.prakriti_previously_filled = answer == "yes"
        if self.prakriti_previously_filled:
            self.ledger.record(
                "prakriti",
                "filled previously, not on this kiosk",
                self.spoken_source,
                evidence=text("prakriti_ask", self.language),
            )
            self.advance()
            return True
        return False

    def answer_prakriti(self, item_id: str, value: str) -> bool:
        """Record one Prakriti answer. Returns True when the questionnaire is finished."""

        item = prakriti.validate(item_id, value)
        self.prakriti_answers[item_id] = value
        self.ledger.record(
            f"prakriti.{item.section}",
            value,
            Source.QUESTIONNAIRE,
            evidence=item.text_for(self.language),
        )
        if prakriti.next_item(self.prakriti_answers) is None:
            self.prakriti_record = prakriti.summarize(self.prakriti_answers)
            self.ledger.record(
                "prakriti",
                str(self.prakriti_record.get("prakriti") or "insufficient answers"),
                Source.QUESTIONNAIRE,
                evidence="Ayush Prakriti questionnaire, 58 items",
            )
            self.advance()
            return True
        return False

    def add_document(
        self,
        lines: list[str],
        seconds: float | None = None,
        confidence: float | None = None,
        handwritten: bool | None = None,
        outbox_handle: str | None = None,
    ) -> None:
        """Record one scanned page.

        `handwritten` is the confidence-tail verdict (None when there was too little text to
        judge). `outbox_handle` names the image the kiosk is holding for the cloud reader; it is
        only set when the page was judged handwritten and the cloud path is enabled, and it is
        what finish() uploads once the record has an intake_id.
        """

        self.documents.append(
            {
                "lines": lines,
                "line_count": len(lines),
                "seconds": seconds,
                "handwritten": handwritten,
                "outbox_handle": outbox_handle,
            }
        )
        for line in lines:
            self.ledger.record(
                "document_line", line, Source.OCR, confidence=confidence, evidence=line
            )

    @property
    def held_document_handles(self) -> list[str]:
        """Images this session is holding for upload once its record has been ingested."""

        return [d["outbox_handle"] for d in self.documents if d.get("outbox_handle")]

    def finish(self, state: PatientState, red_flags: list[RedFlagAlert]) -> dict:
        """Build the doctor's report. Valid from REPORT or EMERGENCY - both need the sheet."""

        from medikiosk.kiosk import report as report_module

        self.report = report_module.build(
            state=state,
            red_flags=red_flags,
            ayurveda=(
                ayurveda.summarize(self.ayurveda_answers, state.age_years)
                if self.ayurveda_answers
                else None
            ),
            prakriti=self.prakriti_record,
            documents=self.documents,
            abha_number=self.abha_number,
            on_behalf_of=self.on_behalf_of,
            past_visits=self.past_visits,
            prefers_ayush=self.prefers_ayush,
            ledger=self.ledger,
        )
        return self.report
