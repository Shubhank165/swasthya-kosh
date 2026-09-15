"""The AYUSH 58-item Prakriti (constitution) questionnaire, and the Prakriti it reports.

This is a different instrument from `ayurveda.py`. That module is Dashavidha Pariksha - the
ten-fold examination, asked at every visit because it describes the patient *today*. Prakriti is
fixed at conception and does not change, so it is asked once in a lifetime and then read back from
the record. Both end up on the vaidya's sheet; only one is re-asked.

The item list is the Prakriti Assessment Scale published by CCRAS (Central Council for Research in
Ayurvedic Sciences, Ministry of Ayush; 2nd edition 2020, ISBN 978-93-83864-21-8). The form numbers
its items 1 to 58 but skips 51 and uses 53 twice, so there are exactly 58 questions.

What this module reports: the seven Prakriti of the classical texts - three single-dosha (Vataja,
Pittaja, Kaphaja), three dual (Vata-Pittaja, Pitta-Kaphaja, Vata-Kaphaja), and Sama where the three
are in balance. Not ten: the ten-fold thing in Ayurveda is Dashavidha Pariksha, which is the other
module.

ON THE SCORING WEIGHTS - read before trusting a printed Prakriti:

CCRAS scores each item as one mark to one dosha, or zero. The complete item-to-dosha table is
published only in the printed Manual of Standard Operative Procedures, which is copyright CCRAS
and released to assessors who have completed CCRAS training. Six scoring rules, across five
items, are stated outright in the public preview of that manual and are used here verbatim -
their choices are marked `official=True`. (The preview states two more, for built and height,
which the kiosk cannot measure.) Every other weight is derived from the classical descriptions
the manual itself cites (Charaka Samhita Vimana Sthana 8/96-98, Sushruta Samhita Sharira Sthana 4,
Ashtanga Hridaya Sharira Sthana 3) and is marked `official=False`.

So: the questions are the AYUSH instrument; the scoring is a faithful reconstruction of it and has
not been reviewed by a vaidya. `summarize()` returns `scoring_reviewed: False` and the report
prints the Prakriti as provisional. Running the certified scale requires CCRAS training and their
table - swapping the weights in `ITEMS` below is the whole change, which is why they are one flat
readable table and not logic spread through the module.

Every one of the 58 is asked. Sixteen of them cannot be put to a patient the way CCRAS puts them
to an assessor, and those are asked as the nearest honest self-report instead:

  - traits an assessor observes or palpates (skin colour and texture, moles, visible veins,
    forehead width, eyelashes, hair density and colour, skin temperature) are asked of the
    patient about their own body, which they can answer by looking;
  - the four mental faculties CCRAS measures with printed cards - a prose passage, a five-word
    recall list, picture and figure cards - are asked as the patient's own report of the same
    classical trait, because those materials are published only in the copyrighted manual;
  - the two items that accept several answers at once (addiction, skin texture) are asked one
    trait at a time, which is closer to the scale's own arithmetic than forcing a single pick,
    since CCRAS awards a mark per trait rather than per question.

Each carries `proxy=` naming what it stands in for, and `summarize()` lists every one the patient
actually answered under `self_reported`. A self-reported trait is weaker evidence than an examined
one and the sheet says which is which, so a doubtful Prakriti can be re-examined at those items
rather than re-run from the top.

Built and height are the only things left outstanding: the scale scores them from a weighing scale
and a stadiometer, and a patient's estimate of their own build is a different measurement wearing
the same name.
"""

from __future__ import annotations

from dataclasses import dataclass

VATA, PITTA, KAPHA = "vata", "pitta", "kapha"
DOSHAS = (VATA, PITTA, KAPHA)

# The seven Prakriti. Keyed by the sorted dosha tuple that produces them.
PRAKRITI_NAMES: dict[tuple[str, ...], dict[str, str]] = {
    (VATA,): {"en": "Vataja", "hi": "वातज"},
    (PITTA,): {"en": "Pittaja", "hi": "पित्तज"},
    (KAPHA,): {"en": "Kaphaja", "hi": "कफज"},
    (PITTA, VATA): {"en": "Vata-Pittaja", "hi": "वात-पित्तज"},
    (KAPHA, PITTA): {"en": "Pitta-Kaphaja", "hi": "पित्त-कफज"},
    (KAPHA, VATA): {"en": "Vata-Kaphaja", "hi": "वात-कफज"},
    (KAPHA, PITTA, VATA): {"en": "Sama (tridoshaja)", "hi": "सम (त्रिदोषज)"},
}


@dataclass(frozen=True)
class Choice:
    value: str
    en: str
    hi: str
    dosha: str | None = None
    icon: str = "circle"
    # True only where the CCRAS public preview states this mark explicitly. See module docstring.
    official: bool = False

    def label_for(self, language: str | None) -> str:
        # Only English and Hindi are printed on the CCRAS form. Rather than machine-translate
        # clinical wording nobody has reviewed, the other seven languages fall back to English -
        # the same rule flow.SCREEN_TEXT already follows, and the pre-render step gives those
        # fallbacks the English voice so they stay intelligible.
        return self.hi if (language or "en")[:2] == "hi" else self.en


@dataclass(frozen=True)
class Item:
    """One question on the form. `number` is the form's own numbering, quirks included."""

    id: str
    number: str
    section: str
    en: str
    hi: str
    choices: tuple[Choice, ...]
    # Set where the kiosk asks the patient something the CCRAS scale has an assessor observe or
    # test with printed materials. The answer still counts, but it is self-reported, and the
    # record says so rather than passing it off as an examination finding.
    proxy: str | None = None

    def text_for(self, language: str | None) -> str:
        return self.hi if (language or "en")[:2] == "hi" else self.en

    def options_for(self, language: str | None) -> list[dict[str, str]]:
        return [
            {"value": c.value, "label": c.label_for(language), "icon": c.icon}
            for c in self.choices
        ]


@dataclass(frozen=True)
class Pending:
    """A form item the kiosk does not ask, and the reason it cannot."""

    number: str
    en: str
    reason: str
    kind: str  # "assessor" | "materials" | "unsupported_input"


# --------------------------------------------------------------------------- not asked

# Nothing on the form is left unasked. This stays because the shape is still needed for the two
# items below, and because a future edit that cannot ask something must record why here rather
# than dropping it.
PENDING: tuple[Pending, ...] = ()

# Built and height are scored by the scale from measurements (Apachita = Vata, Upachita = Kapha;
# tall or short = Vata, medium = 0) rather than from anything the patient is asked. They carry no
# number on the form. A kiosk with no scale and no stadiometer cannot produce them, and asking a
# patient to estimate their own build is a different measurement wearing the same name - so they
# are reported as outstanding for the vaidya instead.
MEASURED: tuple[str, ...] = ("Built (Apachita / Upachita)", "Height (tall / short / medium)")


# --------------------------------------------------------------------------- the questionnaire
#
# Order and numbering follow the CCRAS form. `official=True` marks the ten weights quoted verbatim
# from the public preview of the CCRAS manual; every other weight is derived from the classical
# references that manual cites and is awaiting a vaidya's review.


def _c(value: str, en: str, hi: str, dosha: str | None = None, icon: str = "circle",
       official: bool = False) -> Choice:
    return Choice(value, en, hi, dosha, icon, official)


YES_NO_VATA = (
    _c("yes", "Yes", "हाँ", VATA, "check"),
    _c("no", "No", "नहीं", None, "cross"),
)
YES_NO_PITTA = (
    _c("yes", "Yes", "हाँ", PITTA, "check"),
    _c("no", "No", "नहीं", None, "cross"),
)
YES_NO_NONE = (
    _c("yes", "Yes", "हाँ", None, "check"),
    _c("no", "No", "नहीं", None, "cross"),
)

ITEMS: tuple[Item, ...] = (
    # ------------------------------------------------------------------ 1-8  demographics
    # No dosha marks. They are on the form, they go on the vaidya's sheet, and they score nothing.
    Item("pk_marital", "1", "demographic",
         "Marital status", "वैवाहिक स्थिति",
         (_c("married", "Married", "विवाहित", icon="rings"),
          _c("unmarried", "Unmarried", "अविवाहित", icon="person"),
          _c("divorcee", "Divorcee", "तलाकशुदा", icon="person"),
          _c("widow", "Widow / widower", "विधवा / विधुर", icon="person"))),
    Item("pk_occupation", "2", "demographic",
         "Occupation", "उपजीविका",
         (_c("desk", "Desk work", "डेस्क कार्य", icon="desk"),
          _c("field", "Field work", "क्षेत्र कार्य", icon="field"),
          _c("homemaker", "Homemaker", "गृहिणी", icon="home"),
          _c("student", "Student", "छात्र", icon="book"),
          _c("other", "Other", "अन्य", icon="dots"))),
    Item("pk_religion", "3", "demographic",
         "Religion", "धर्म",
         (_c("hindu", "Hindu", "हिन्दू", icon="circle"),
          _c("muslim", "Muslim", "मुस्लिम", icon="circle"),
          _c("christian", "Christian", "ईसाई", icon="circle"),
          _c("sikh", "Sikh", "सिख", icon="circle"),
          _c("other", "Other", "अन्य", icon="dots"),
          _c("undisclosed", "Prefer not to say", "बताना नहीं चाहते", icon="cross"))),
    Item("pk_diet", "4", "demographic",
         "Diet", "आहार",
         (_c("vegetarian", "Vegetarian", "निरामिष", icon="leaf"),
          _c("mixed", "Mixed", "मिश्रित", icon="plate"))),
    Item("pk_family_type", "6", "demographic",
         "Type of family", "परिवार का प्रकार",
         (_c("nuclear", "Nuclear", "एकल", icon="home"),
          _c("joint", "Joint", "संयुक्त", icon="group"))),
    Item("pk_income", "8", "demographic",
         "Total income of the family per year", "परिवार की वार्षिक आय",
         (_c("under_1l", "Below 1 lakh", "1 लाख से कम", icon="coin"),
          _c("1l_3l", "1 to 3 lakh", "1 से 3 लाख", icon="coin"),
          _c("3l_5l", "3 to 5 lakh", "3 से 5 लाख", icon="coin"),
          _c("above_5l", "Above 5 lakh", "5 लाख से अधिक", icon="coin"),
          _c("undisclosed", "Prefer not to say", "बताना नहीं चाहते", icon="cross"))),

    # ------------------------------------------------------------------ 9  data quality gate
    Item("pk_weight_confounder", "9", "physical",
         "Is anything currently affecting your weight (illness, pregnancy, recent treatment)?",
         "क्या इस समय आपके वजन को प्रभावित करने वाला कोई कारण है?",
         (_c("yes", "Yes", "हाँ", icon="check"),
          _c("no", "No", "नहीं", icon="cross"))),

    # ------------------------------------------------------------------ 15-25  physical traits
    Item("pk_wrinkles", "15", "physical",
         "Do you get wrinkles early (Kshipravali)?", "क्या आपको जल्दी झुर्रियाँ पड़ती हैं?",
         YES_NO_VATA),
    Item("pk_joint_sounds", "17", "physical",
         "Is there any sound on normal movement of knee, ankle, toes or shoulder?",
         "क्या सामान्य गतिविधि में घुटने/टखने/पाँव के अंगूठे या कंधे से आवाज़ होती है?",
         YES_NO_VATA),
    Item("pk_eye_dryness", "18.1", "physical",
         "Do your eyes feel rough or dry?", "क्या आँखों में खुरदरापन या सूखापन महसूस होता है?",
         YES_NO_VATA),
    Item("pk_eye_irritation", "18.2", "physical",
         "Do your eyes burn or sting?", "क्या आँखों में जलन या चुभन होती है?",
         YES_NO_PITTA),
    Item("pk_eye_fatigue", "18.3", "physical",
         "Do your eyes get tired?", "क्या आँखों में थकान होती है?",
         YES_NO_VATA),
    Item("pk_eye_blinking", "18.4", "physical",
         "Do you blink frequently?", "क्या आप बार-बार आँखें झपकाते हैं?",
         YES_NO_VATA),
    Item("pk_eye_redness", "20", "physical",
         "Do your eyes redden with anger, after alcohol, or in sunlight?",
         "क्या आपकी आँखें गुस्से में / मद्यपान के बाद / धूप में लाल हो जाती हैं?",
         YES_NO_PITTA),
    Item("pk_hair_texture", "21", "physical",
         "What is your body hair like?", "आपके शरीर के बाल कैसे हैं?",
         (_c("rough_dry", "Rough, dry, or with split ends", "परुष / रूक्ष / स्फुटित", VATA, "hair"),
          _c("oily", "Oily (Snigdha)", "स्निग्ध (तैलीय)", KAPHA, "hair"),
          _c("soft", "Soft (Mridu)", "मृदु (मुलायम)", PITTA, "hair"),
          _c("none", "None of these", "इनमें से कोई नहीं", None, "cross"))),
    Item("pk_hair_curly", "22", "physical",
         "Is your hair curly (Kutila kesha)?", "क्या आपके बाल घुंघराले हैं?",
         YES_NO_VATA),
    Item("pk_greying", "25.1", "physical",
         "Did you have grey hair (more than about 20%) before the age of 35?",
         "क्या 35 वर्ष की आयु से पहले आपके लगभग 20% से अधिक बाल सफ़ेद हो गए थे?",
         YES_NO_PITTA),
    Item("pk_baldness", "25.2", "physical",
         "Have you had significant hair loss or baldness (more than about 50%) before 50?",
         "क्या 50 वर्ष की आयु से पहले आपके लगभग 50% से अधिक बाल झड़ गए / गंजापन हुआ?",
         YES_NO_PITTA),
    # ------------------------------------------------------------------ 26-40  physiology
    Item("pk_meal_frequency", "26", "physiology",
         "How many main meals and how many refreshments do you take in a day?",
         "एक दिन में कितनी बार मुख्य आहार और कितनी बार जलपान लेते हैं?",
         (_c("2_meals_3_snacks", "2 main meals and 3 or more refreshments",
             "2 मुख्य भोजन और 3 या अधिक जलपान", PITTA, "plate"),
          _c("3_meals_2_snacks", "3 main meals and 2 refreshments",
             "3 मुख्य भोजन और 2 जलपान", None, "plate"),
          _c("none", "Neither of these", "इनमें से कोई नहीं", None, "cross"))),
    Item("pk_food_quantity", "27", "physiology",
         "How much food do you eat in a day?", "आप दिनभर में भोजन की कितनी मात्रा लेते हैं?",
         (_c("less", "Less than average (about 4 chapatti, little rice, one bowl dal)",
             "औसत से कम (लगभग 4 रोटी, थोड़े चावल, 1 कटोरी दाल)", VATA, "plate_small"),
          _c("average", "Average (6 to 10 chapatti, rice, dal, vegetables, fruit)",
             "औसत (6-10 रोटी, चावल, दाल, सब्ज़ी, फल)", None, "plate"),
          _c("more", "More than average", "औसत से अधिक", PITTA, "plate_large"))),
    Item("pk_skip_meal", "28", "physiology",
         "If you skip a meal, can you tolerate it easily?",
         "यदि आप एक समय का भोजन छोड़ दें, तो क्या आप आसानी से सहन कर पाते हैं?",
         (_c("tolerate", "Can tolerate", "सहन कर सकते हैं", KAPHA, "check"),
          _c("cannot", "Cannot tolerate", "सहन नहीं कर सकते", PITTA, "cross"),
          _c("varies", "It varies", "यह बदलता रहता है", VATA, "dots"))),
    Item("pk_eating_speed", "29", "physiology",
         "Eating with family or friends, when do you usually finish?",
         "परिवार या मित्रों के साथ भोजन करते समय आप आमतौर पर कब समाप्त करते हैं?",
         # Official: fast eating (Laghu / Chapala Ahara) = Vata; slow eating (Manda ahara) = Kapha.
         (_c("first", "Before the others", "सबसे पहले", VATA, "fast", official=True),
          _c("at_par", "At about the same time", "साथ-साथ", None, "circle", official=True),
          _c("last", "Last", "सबसे अन्त में", KAPHA, "slow", official=True))),
    Item("pk_thirst_reaction", "30", "physiology",
         "When you feel thirsty and water is not immediately available, what do you do?",
         "जब प्यास लगी हो और पानी तुरंत उपलब्ध न हो, आपकी क्या प्रतिक्रिया होगी?",
         (_c("search", "Look for water straight away", "तुरंत पानी की तलाश करेंगे", PITTA, "water"),
          _c("wait", "Wait a while", "कुछ देर इन्तज़ार करेंगे", None, "clock"))),
    Item("pk_water_quantity", "31", "physiology",
         "About how much water or fluid do you drink per day?",
         "आप एक दिन में लगभग कितना पानी या तरल पदार्थ लेते हैं?",
         (_c("under_1l", "Less than 1 litre", "1 लीटर से कम", KAPHA, "water_low"),
          _c("1_2l", "1 to 2 litres", "1 से 2 लीटर", None, "water"),
          _c("over_2l", "More than 2 litres", "2 लीटर से ज़्यादा", PITTA, "water_high"))),
    Item("pk_water_frequency", "32", "physiology",
         "How many times a day do you drink water or fluids?",
         "आप एक दिन में कितनी बार पानी या तरल पदार्थ लेते हैं?",
         (_c("upto_4", "4 times or fewer", "4 बार या उससे कम", KAPHA, "water_low"),
          _c("5_7", "5 to 7 times", "5 से 7 बार", None, "water"),
          _c("over_7", "More than 7 times", "7 बार से ज़्यादा", PITTA, "water_high"))),
    Item("pk_stool_quantity", "33", "physiology",
         "Compared with how much you eat, how much stool do you pass?",
         "भोजन की तुलना में आप कितनी मात्रा में मल त्याग करते हैं?",
         (_c("adequate", "Adequate or bulky", "यथोचित / ज़्यादा", KAPHA, "circle"),
          _c("less", "Less", "कम", VATA, "circle_small"))),
    Item("pk_bowel_ease", "34", "physiology",
         "Do you pass stool easily and quickly, without constipation or laxatives?",
         "क्या आपको कब्ज या रेचक औषधि के बिना आसानी से मल त्याग हो जाता है?",
         (_c("rarely", "Rarely", "कदाचित् / शायद ही", VATA, "cross"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("often", "Often", "प्रायः / अक्सर", PITTA, "check"))),
    Item("pk_sweating", "35", "physiology",
         "How much do you sweat in the sun, or on exercise or physical work?",
         "धूप में या व्यायाम/शारीरिक श्रम करने पर आपको कितना पसीना आता है?",
         (_c("profuse", "A lot", "बहुत अधिक", PITTA, "drop_large"),
          _c("medium", "A moderate amount", "मध्यम", None, "drop"),
          _c("scanty", "Very little", "अल्प", VATA, "drop_small"))),
    Item("pk_body_odour", "36", "physiology",
         "Is your body odour strong or mild?", "आपके शरीर की गन्ध कैसी है?",
         (_c("strong", "Strong", "तीक्ष्ण", PITTA, "circle"),
          _c("mild", "Mild", "हल्की", None, "circle_small"))),
    Item("pk_odour_reported", "37", "physiology",
         "Has a family member or friend ever mentioned a strong body odour?",
         "क्या परिवार के किसी सदस्य या मित्र ने आपको शरीर की तेज़ गन्ध के बारे में बताया है?",
         YES_NO_PITTA),
    Item("pk_light_sleep", "38", "physiology",
         "Does a small noise wake you while you are sleeping?",
         "क्या सोते समय आप थोड़ी सी आवाज़ से भी उठ जाते हैं?",
         (_c("rarely", "Rarely", "कदाचित् / शायद ही", KAPHA, "sleep_deep"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("often", "Often", "प्रायः / अक्सर", VATA, "sleep_light"))),
    Item("pk_sleep_hours", "39", "physiology",
         "How many hours do you sleep in 24 hours?",
         "आप 24 घण्टों में कितने घण्टे सोते हैं?",
         (_c("under_6", "Less than 6 hours", "6 घण्टों से कम", VATA, "sleep_light"),
          _c("6_8", "6 to 8 hours", "6-8 घण्टे", None, "sleep"),
          _c("over_8", "More than 8 hours", "8 घण्टों से ज़्यादा", KAPHA, "sleep_deep"))),
    Item("pk_dreams", "40", "physiology",
         "Do you often dream, and remember your dreams?",
         "क्या आप प्रायः सपने देखते हैं और उन्हें याद रखते हैं?",
         YES_NO_VATA),

    # ------------------------------------------------------------------ 41-58  mental (Satva)
    Item("pk_indecisive", "41", "mental",
         "After taking a decision, how often do you feel the need to change it?",
         "निर्णय लेने के बाद क्या आपको निर्णय बदलने की आवश्यकता होती है?",
         # Official: answering "Often" is indecisiveness (Anavasthita atma), Vata = 1 mark.
         (_c("rarely", "Rarely", "कदाचित् / शायद ही", None, "check", official=True),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots", official=True),
          _c("often", "Often", "प्रायः / अक्सर", VATA, "cross", official=True))),
    Item("pk_relations_last", "44", "mental",
         "Do your relationships with friends, relatives and neighbours last a long time?",
         "क्या आपके मित्रों / रिश्तेदारों / पड़ोसियों से सम्बन्ध लम्बे समय तक बने रहते हैं?",
         (_c("rarely", "Rarely", "कदाचित् / शायद ही", VATA, "cross"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("often", "Often", "प्रायः / अक्सर", KAPHA, "check"))),
    Item("pk_queue_reaction", "48", "mental",
         "What do you do if someone breaks a queue in front of you?",
         "यदि कोई व्यक्ति आपके सामने कतार तोड़ता है तो आपकी क्या प्रतिक्रिया होगी?",
         (_c("calm", "Ignore it, stay calm, or ask them politely",
             "नज़रअंदाज़ कर देंगे / शान्त रहेंगे / अनुरोध करेंगे", KAPHA, "calm"),
          _c("argue", "Argue, shout, or lose your temper",
             "बहस करेंगे / चिल्लायेंगे / आपे से बाहर हो जायेंगे", PITTA, "angry"),
          _c("quick_anger", "Get angry quickly, then calm down quickly",
             "गुस्सा करेंगे, फिर शीघ्र शान्त हो जायेंगे", VATA, "spark"))),
    Item("pk_family_opinion", "49", "mental",
         "What do your family, friends and relatives say you are like?",
         "आपके परिवार / मित्रों / रिश्तेदारों की आपके बारे में क्या राय है?",
         (_c("calm", "Usually calm", "आमतौर पर शान्त स्वभाव", KAPHA, "calm"),
          _c("short_tempered", "Short tempered", "चिड़चिड़ा स्वभाव", PITTA, "angry"),
          _c("quick_anger", "Angry quickly, then calm quickly",
             "शीघ्र उत्तेजित, फिर शीघ्र शान्त", VATA, "spark"))),
    Item("pk_talkative", "50", "mental",
         "Are you talkative (Vachala)?", "क्या आप वाचाल हैं (बहुत बातें करते हैं)?",
         YES_NO_VATA),
    Item("pk_soft_spoken", "52", "mental",
         "Do you speak little, and softly (Mitavak)?", "क्या आप कम और धीरे बोलते हैं (मितवाक्)?",
         (_c("yes", "Yes", "हाँ", KAPHA, "check"),
          _c("no", "No", "नहीं", None, "cross"))),
    Item("pk_orator", "53a", "mental",
         "Can you speak at length and effectively on a topic of your choice?",
         "क्या आप अपनी पसन्द के किसी विषय पर प्रभावपूर्ण ढंग से बहुत देर तक बात कर सकते हैं?",
         (_c("rarely", "Rarely", "कदाचित् / शायद ही", None, "cross"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("often", "Often", "प्रायः / अक्सर", PITTA, "check"))),
    Item("pk_dominant_speaker", "53b", "mental",
         "In a discussion among friends or colleagues, can you dominate and establish your view?",
         "मित्रों/सहकर्मियों के बीच चर्चा में क्या आप अपना मत स्थापित कर पाते हैं?",
         (_c("rarely", "Rarely", "कदाचित् / शायद ही", None, "cross"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("often", "Often", "प्रायः / अक्सर", PITTA, "check"))),
    Item("pk_stands_by_values", "54", "mental",
         "Do you have the strength to stand by your values whatever others think or say?",
         "क्या आपमें अपने विश्वास / मूल्यों के पक्ष में खड़े रहने का सामर्थ्य है?",
         (_c("rarely", "Rarely", "कदाचित् / शायद ही", None, "cross"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("often", "Often", "प्रायः / अक्सर", PITTA, "check"))),
    Item("pk_adversity", "55", "mental",
         "Faced with a very difficult situation, what do you usually do?",
         "अत्यन्त प्रतिकूल परिस्थिति का सामना करने पर आप आमतौर पर क्या करते हैं?",
         (_c("run", "Try to get away from it", "भाग जाने की कोशिश करते हैं", VATA, "run"),
          _c("panic", "Become panicky or uneasy", "आतंकित / बेचैन हो जाते हैं", VATA, "spark"),
          _c("face", "Face it bravely until the goal is achieved",
             "लक्ष्य की प्राप्ति तक साहस से सामना करते हैं", PITTA, "shield"))),
    Item("pk_food_preference", "56", "mental",
         "In moderate weather, which food do you prefer?",
         "सामान्य मौसम में आप किस प्रकार के खाद्य पदार्थ ज़्यादा पसन्द करते हैं?",
         (_c("cold", "Cold food and drinks over hot",
             "शीतल खाद्य एवं पेय पदार्थ", PITTA, "snowflake"),
          _c("hot", "Hot food and drinks over cold",
             "गर्म खाद्य एवं पेय पदार्थ", VATA, "flame"),
          _c("none", "Neither", "उपरोक्त में से कोई नहीं", None, "cross"))),
    Item("pk_enmity", "57", "mental",
         "Is there a friend, relative or colleague you fell out with and never made up with?",
         "क्या कोई मित्र / रिश्तेदार / सहकर्मी है जिनसे मतभेद के बाद कभी सुलह नहीं हो पाई?",
         # Official: strong enmity (Dridhavairam), Kapha = 1 mark.
         (_c("yes", "Yes", "हाँ", KAPHA, "check", official=True),
          _c("no", "No", "नहीं", None, "cross", official=True))),
    Item("pk_polite", "58", "mental",
         "Do you stay polite even in stressful or anxious situations?",
         "क्या आप तनावपूर्ण / चिंताजनक स्थिति में भी विनम्र रह पाते हैं?",
         # Official: polite and humble (Vineeta), Kapha = 1 mark.
         (_c("rarely", "Rarely", "कदाचित् / शायद ही", None, "cross", official=True),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots", official=True),
          _c("often", "Often", "प्रायः / अक्सर", KAPHA, "check", official=True))),
    # ------------------------------------------------------------------ 5, 7  demographics
    # The form lets a patient tick several addictions at once. Asked here one substance at a
    # time: the kiosk has no multi-select control, and a substance the patient uses is a fact
    # the vaidya wants either way. Scores nothing.
    Item("pk_alcohol", "5.1", "demographic",
         "Do you drink alcohol?", "क्या आप मद्यसार (शराब) लेते हैं?",
         YES_NO_NONE),
    Item("pk_tea_coffee", "5.2", "demographic",
         "Do you drink tea or coffee?", "क्या आप चाय या कॉफ़ी लेते हैं?",
         YES_NO_NONE),
    Item("pk_pan", "5.3", "demographic",
         "Do you chew pan?", "क्या आप पान चबाते हैं?",
         YES_NO_NONE),
    Item("pk_smoking", "5.4", "demographic",
         "Do you smoke?", "क्या आप धूम्रपान करते हैं?",
         YES_NO_NONE),
    Item("pk_tobacco", "5.5", "demographic",
         "Do you use tobacco?", "क्या आप तंबाकू का सेवन करते हैं?",
         YES_NO_NONE),
    Item("pk_family_size", "7", "demographic",
         "How many people are there in your family?", "आपके परिवार में कितने सदस्य हैं?",
         # Bands rather than a typed number: the kiosk answers in pictures and speech, and the
         # exact count carries no dosha mark.
         (_c("1_2", "1 to 2", "1 से 2", None, "group"),
          _c("3_4", "3 to 4", "3 से 4", None, "group"),
          _c("5_6", "5 to 6", "5 से 6", None, "group"),
          _c("7_plus", "7 or more", "7 या अधिक", None, "group"))),

    # ------------------------------------------------------------------ 10-24  observed traits
    # The CCRAS manual has an assessor observe these. A kiosk has no assessor, so they are asked
    # of the patient about their own body - answerable by looking, and better than a Prakriti
    # computed from a questionnaire with nine holes in it. Marked `proxy` so the sheet can say
    # which answers were self-reported rather than observed.
    Item("pk_veins", "10", "physical",
         "Are the tendons and veins on the backs of your hands and feet easy to see?",
         "क्या आपके हाथ-पैर की नसें और कण्डराएँ आसानी से दिखाई देती हैं?",
         # Official: prominent tendons and veins, Vata = 1 mark.
         (_c("yes", "Yes", "हाँ", VATA, "check", official=True),
          _c("no", "No", "नहीं", None, "cross", official=True)),
         proxy="the manual has the assessor observe this on exposed skin"),
    Item("pk_forehead", "11", "physical",
         "Place four fingers sideways on your forehead. Is your forehead wider than that?",
         "अपनी चार अंगुलियाँ माथे पर आड़ी रखें। क्या आपका माथा उससे चौड़ा है?",
         (_c("broader", "Wider than four fingers", "चार अंगुल से अधिक चौड़ा", KAPHA, "check"),
          _c("upto", "Four fingers or less", "चार अंगुल या उससे कम", None, "cross")),
         proxy="the manual measures this in angula against the patient's own finger-breadth"),
    Item("pk_skin_colour", "12", "physical",
         "How would you describe your natural skin colour?",
         "आपकी त्वचा का स्वाभाविक वर्ण कैसा है?",
         (_c("gaur", "Fair, like a lotus or straw", "गौर (कमल / तिनके जैसा)", KAPHA, "circle"),
          _c("gaur_pitanga", "Fair with a yellowish tinge", "गौर पीतांग (पीत आभा सहित)",
             PITTA, "circle"),
          _c("dhusara", "Dusky", "धूसर (धुंधला / श्यामल)", VATA, "circle"),
          _c("krishna", "Dark", "कृष्ण (काला वर्ण)", VATA, "circle")),
         proxy="assessor observation"),
    # The form takes several skin textures at once, and CCRAS scores a mark per texture, so each
    # is asked on its own. That is closer to the scale's own arithmetic than making the patient
    # pick one.
    Item("pk_skin_dry", "13.1", "physical",
         "Is your skin dry, or without shine?", "क्या आपकी त्वचा रूखी / कान्ति रहित है?",
         YES_NO_VATA, proxy="assessor observation"),
    Item("pk_skin_cracking", "13.2", "physical",
         "Does your skin crack, other than on the soles and palms?",
         "क्या तलवों और हथेलियों के अलावा आपकी त्वचा फटती है?",
         YES_NO_VATA, proxy="assessor observation"),
    Item("pk_skin_smooth", "13.3", "physical",
         "Is your skin smooth and soft, without dryness or blemishes?",
         "क्या आपकी त्वचा चिकनी, मुलायम और रूक्षता रहित है?",
         (_c("yes", "Yes", "हाँ", KAPHA, "check"),
          _c("no", "No", "नहीं", None, "cross")),
         proxy="assessor observation"),
    Item("pk_moles", "14", "physical",
         "Do you have moles, freckles or dark patches on your skin?",
         "क्या आपकी त्वचा पर तिल, छाइयाँ या झाइयाँ हैं?",
         YES_NO_PITTA, proxy="assessor observation"),
    Item("pk_skin_temp", "16", "physical",
         "Does your skin usually feel warm, cold, or neither?",
         "आपकी त्वचा आमतौर पर गर्म लगती है, शीतल, या सामान्य?",
         (_c("warm", "Warm", "गर्म", PITTA, "flame"),
          _c("cold", "Cold", "शीतल", VATA, "snowflake"),
          _c("normal", "Neither", "सामान्य", None, "circle")),
         proxy="the assessor palpates the back of the hand"),
    Item("pk_eyelashes", "19", "physical",
         "Are your eyelashes thin and few, thick and dense, or in between?",
         "आपकी पलकें कैसी हैं - अल्प, घनी, या मध्यम?",
         (_c("scanty", "Thin and few", "अल्प / पतली", VATA, "circle_small"),
          _c("dense", "Thick and dense", "घनी", KAPHA, "circle"),
          _c("medium", "In between", "सामान्य", None, "dots")),
         proxy="assessor observation"),
    Item("pk_hair_density", "23", "physical",
         "Is your hair sparse, dense, or in between?",
         "आपके बाल कैसे हैं - अल्प, घने, या मध्यम?",
         (_c("scanty", "Sparse", "अल्प केश", PITTA, "circle_small"),
          _c("dense", "Dense", "घन केश", KAPHA, "circle"),
          _c("medium", "In between", "मध्यम", None, "dots")),
         proxy="assessor observation"),
    Item("pk_hair_colour", "24", "physical",
         "Before any greying, what colour was your hair?",
         "सफ़ेद होने से पहले आपके बालों का रंग कैसा था?",
         (_c("black", "Black", "श्याम केश (काले बाल)", KAPHA, "circle"),
          _c("reddish_brown", "Reddish brown", "कपिल केश (लाल-भूरे बाल)", PITTA, "circle"),
          _c("dusky", "Dusky brown", "धूसर केश (श्यामल बाल)", VATA, "circle")),
         proxy="assessor observation; the form also records it for anyone using hair dye"),

    # ------------------------------------------------------------------ 42-47  mental faculties
    # CCRAS measures these with printed materials the assessor administers - a prose passage, a
    # five-word recall list, and picture, figure and shape cards. Those materials are published
    # only in the copyrighted manual, so the kiosk cannot run the test itself. What it asks
    # instead is the patient's own report of the same classical trait: Grahana shakti (grasp),
    # Dharana shakti (retention), Nipunamati (skill) and Medha (intellect). That is a weaker
    # instrument than the card test and is marked `proxy` so nobody reads it as one.
    Item("pk_comprehension", "42", "mental",
         "When something new is explained to you, do you usually grasp it quickly?",
         "जब आपको कुछ नया समझाया जाता है, क्या आप उसे शीघ्र समझ लेते हैं?",
         (_c("quick", "Quickly", "शीघ्र (श्रुतग्राही)", PITTA, "check"),
          _c("slow", "Slowly, but then it stays", "धीरे, पर फिर याद रहता है (चिरग्राही)",
             KAPHA, "dots"),
          _c("varies", "It varies", "यह बदलता रहता है", VATA, "cross")),
         proxy="CCRAS administers a prose comprehension test with printed material"),
    Item("pk_memory", "43", "mental",
         "Do you remember things you were told long ago?",
         "क्या आपको बहुत पहले बताई गई बातें याद रहती हैं?",
         (_c("often", "Yes, for a long time", "हाँ, लम्बे समय तक", KAPHA, "check"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("rarely", "I forget quickly", "मैं जल्दी भूल जाता हूँ", VATA, "cross")),
         proxy="CCRAS administers a five-word and paired-word recall test"),
    Item("pk_skill", "45", "mental",
         "Do you pick up new practical skills easily - a tool, a craft, a machine?",
         "क्या आप नए व्यावहारिक कौशल आसानी से सीख लेते हैं?",
         (_c("often", "Yes, easily", "हाँ, आसानी से (निपुणमति)", PITTA, "check"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("rarely", "I find it hard", "मुझे कठिन लगता है", VATA, "cross")),
         proxy="CCRAS uses printed picture cards for Nipunamati"),
    Item("pk_reasoning", "46", "mental",
         "When you face a problem with no obvious answer, do you usually work it out?",
         "जब कोई समस्या हो जिसका उत्तर स्पष्ट न हो, क्या आप उसे सुलझा लेते हैं?",
         (_c("often", "Usually", "प्रायः (मेधावी)", PITTA, "check"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("rarely", "Rarely", "कदाचित्", VATA, "cross")),
         proxy="CCRAS uses printed problem-figure cards for Medhavi"),
    Item("pk_shapes", "47", "mental",
         "Do you notice patterns and shapes quickly - a repeated design, a shape out of place?",
         "क्या आप आकृतियों और नमूनों को शीघ्र पहचान लेते हैं?",
         (_c("often", "Usually", "प्रायः", PITTA, "check"),
          _c("sometimes", "Sometimes", "कभी-कभी", None, "dots"),
          _c("rarely", "Rarely", "कदाचित्", VATA, "cross")),
         proxy="CCRAS uses printed shape cards"),
)

BY_ID: dict[str, Item] = {item.id: item for item in ITEMS}

# The form's own item count: what the kiosk asks, plus what it records as pending, plus the two
# scored from body measurements. Asserted in the tests so an edit cannot quietly drop a question.
FORM_ITEM_COUNT = 58


# --------------------------------------------------------------------------- coverage

# Form numbers that carry sub-questions: the form counts each as one item, this module asks each
# sub-question separately because they take separate answers.
SUBDIVIDED = {"18": 4, "25": 2}
# 53 is printed twice on the form - two different questions, both numbered 53.
REPEATED = {"53": 2}
SKIPPED_BY_FORM = "51"


def form_numbers() -> set[str]:
    """Top-level form numbers this module accounts for, asked or pending."""

    return {
        item.number.split(".")[0].rstrip("ab")
        for item in ITEMS
    } | {pending.number.split(".")[0] for pending in PENDING}


def coverage() -> dict[str, object]:
    """Reconcile what this module holds against the form's own count of 58.

    The form numbers 1 to 58 but skips 51 and prints 53 twice, so 57 numbers carry 58 questions.
    Built and height are scored from measurements and carry no number of their own.
    """

    covered = form_numbers()
    expected = {str(n) for n in range(1, 59)} - {SKIPPED_BY_FORM}
    questions = len(covered) + sum(extra - 1 for extra in REPEATED.values())
    return {
        "form_numbers_covered": len(covered),
        "questions": questions,
        "missing": sorted(expected - covered, key=int),
        "unexpected": sorted(covered - expected, key=int),
        "asked": len(ITEMS),
        "pending": len(PENDING),
        "measured": len(MEASURED),
    }


# --------------------------------------------------------------------------- asking

def next_item(answers: dict[str, str]) -> Item | None:
    for item in ITEMS:
        if item.id not in answers:
            return item
    return None


def validate(item_id: str, value: str) -> Item:
    """Resolve an answer to its item, or raise. Keeps a bad client from poisoning the record."""

    item = BY_ID.get(item_id)
    if item is None:
        raise ValueError(f"unknown prakriti item: {item_id}")
    if value not in {choice.value for choice in item.choices}:
        raise ValueError(f"unknown option {value!r} for {item_id}")
    return item


# --------------------------------------------------------------------------- scoring

def tally(answers: dict[str, str]) -> dict[str, int]:
    """One mark per answered item to the dosha that item's answer indicates. CCRAS scores this way:
    a mark or nothing, never a weight."""

    marks = dict.fromkeys(DOSHAS, 0)
    for item_id, value in answers.items():
        item = BY_ID.get(item_id)
        if item is None:
            continue
        for choice in item.choices:
            if choice.value == value and choice.dosha:
                marks[choice.dosha] += 1
    return marks


# A dosha counts toward the Prakriti when it holds at least this share of the marks. Two doshas
# clearing it is a dvandvaja (dual) Prakriti; all three is Sama. The threshold is what turns three
# numbers into one of the seven types, and it is the other thing a vaidya should set - CCRAS's own
# cut-offs are in the licensed manual.
DOMINANCE_SHARE = 0.30

# Below this many scored answers the marks are noise, and a Prakriti printed from noise is worse
# than none. Roughly a third of the scoring items.
MIN_SCORED_ANSWERS = 12


def classify(marks: dict[str, int]) -> tuple[str, ...] | None:
    """The doshas that make up the Prakriti, or None when the marks do not support one."""

    total = sum(marks.values())
    if total < MIN_SCORED_ANSWERS:
        return None
    leading = max(marks.values())
    if leading == 0:
        return None
    # Always include the top dosha, then anything close enough to count alongside it.
    chosen = {
        dosha
        for dosha, count in marks.items()
        if count == leading or count >= DOMINANCE_SHARE * total
    }
    return tuple(sorted(chosen))


def summarize(answers: dict[str, str], recorded_at: str | None = None) -> dict[str, object]:
    """The Prakriti record: the marks, the type, and everything the reader needs to distrust it."""

    marks = tally(answers)
    doshas = classify(marks)
    name = PRAKRITI_NAMES.get(doshas) if doshas else None
    total = sum(marks.values())
    scoring_items = sum(1 for item in ITEMS if any(c.dosha for c in item.choices))

    return {
        "prakriti": name["en"] if name else None,
        "prakriti_hi": name["hi"] if name else None,
        "doshas": list(doshas) if doshas else [],
        "marks": marks,
        "total_marks": total,
        "answered": len(answers),
        "asked_total": len(ITEMS),
        "scoring_items": scoring_items,
        # False until a vaidya signs off the weights in ITEMS. The report prints the Prakriti as
        # provisional while this is False - see the module docstring for why it is not True.
        "scoring_reviewed": False,
        "note": (
            "Provisional: item weights are reconstructed from the classical references the CCRAS "
            "manual cites, not from the licensed CCRAS scoring table. Requires vaidya review."
            if name
            else "Insufficient answers to indicate a Prakriti."
        ),
        "pending_assessment": [
            {"number": p.number, "item": p.en, "reason": p.reason, "kind": p.kind}
            for p in PENDING
        ],
        # Answers the patient gave about themselves where the CCRAS scale has an assessor look,
        # palpate, or run a card test. They score exactly like any other answer; the vaidya is
        # told which ones they are so a doubtful Prakriti can be re-examined at the right items.
        "self_reported": [
            {"number": item.number, "item": item.en, "instead_of": item.proxy}
            for item in ITEMS
            if item.proxy and item.id in answers
        ],
        "pending_measurements": list(MEASURED),
        "recorded_at": recorded_at,
    }
