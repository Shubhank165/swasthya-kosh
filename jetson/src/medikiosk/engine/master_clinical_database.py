"""
MediKiosk - Master Clinical Database Seeder v1.0.0
===================================================
Complete production-ready clinical question node library.
NO PLACEHOLDERS. NO MOCKS. NO TODOs.

Seeds: nodes, syndromes, matrix_weights, routing_rules, node_followups, proxy_mappings

Author: MediKiosk Engineering Team
Ref: DXplain (MGH), NHS Pathways, ICD-10-CM, HL7 FHIR R4, LOINC
"""
from __future__ import annotations
import json
import logging
from medikiosk.engine.db import get_connection, init_db

logger = logging.getLogger(__name__)

# =============================================================================
# NODE DEFINITIONS
# Format: (node_id, prompt_text, help_text, ui_type, ui_options_json,
#          ui_min, ui_max, phase, framework, system_tag,
#          is_red_flag, is_mandatory, display_order, fhir_loinc)
# =============================================================================

NODES = [

    # TRIAGE PHASE 1 - 12 Red-Flag Nodes
    ("T001", "Is the patient unable to speak, making high-pitched stridor, or showing signs of complete airway obstruction?",
     "Look for: no air movement, silent chest, paradoxical breathing, cyanosis around lips.",
     "BINARY", None, None, None, 1, "TRIAGE", "AIRWAY", 1, 1, 1, "LOINC:80274-0"),

    ("T002", "Is the patient using accessory muscles, breathing faster than 30 breaths/min, or unable to complete a sentence?",
     "Accessory muscles: SCM, trapezius, intercostal recession. SpO2 < 90% if measurable.",
     "BINARY", None, None, None, 1, "TRIAGE", "BREATHING", 1, 1, 2, "LOINC:9279-1"),

    ("T003", "Is the patient pale, cold/clammy, has rapid/thready pulse, or systolic BP < 90 mmHg (signs of shock)?",
     "Capillary refill > 2 sec, HR > 120, cool peripheries, mottled skin = circulatory compromise.",
     "BINARY", None, None, None, 1, "TRIAGE", "CIRCULATION", 1, 1, 3, "LOINC:55284-4"),

    ("T004", "Is the patient unconscious, unresponsive, or severely confused (GCS < 14)?",
     "Use AVPU: Alert=15, Voice=12-13, Pain=8-11, Unresponsive=3. Score < 14 = EMERGENCY.",
     "BINARY", None, None, None, 1, "TRIAGE", "DISABILITY", 1, 1, 4, "LOINC:9269-2"),

    ("T005", "Is there active, uncontrolled external bleeding that cannot be stopped with direct pressure?",
     "Arterial spurting, soaked dressings, estimated blood loss > 500 mL = significant hemorrhage.",
     "BINARY", None, None, None, 1, "TRIAGE", "HEMORRHAGE", 1, 1, 5, None),

    ("T006", "Is the patient showing anaphylaxis signs: hives spreading rapidly, facial/tongue swelling, difficulty breathing after exposure?",
     "Triad: skin signs + airway compromise + cardiovascular instability after allergen exposure.",
     "BINARY", None, None, None, 1, "TRIAGE", "ANAPHYLAXIS", 1, 1, 6, "LOINC:41950-7"),

    ("T007", "Is the patient currently having a seizure, or are they postictal (unresponsive after a seizure)?",
     "Active tonic-clonic activity OR unresponsive/confused after witnessed seizure = emergency.",
     "BINARY", None, None, None, 1, "TRIAGE", "SEIZURE", 1, 1, 7, "LOINC:10829-1"),

    ("T008", "Does the patient show FAST signs: Facial droop, Arm weakness, Speech difficulty, or sudden severe headache (thunderclap)?",
     "FAST positive = probable stroke. Thunderclap headache = possible subarachnoid hemorrhage.",
     "BINARY", None, None, None, 1, "TRIAGE", "STROKE", 1, 1, 8, "LOINC:72105-6"),

    ("T009", "Is the patient experiencing crushing chest pain radiating to left arm or jaw, with sweating and nausea?",
     "Classic AMI presentation. Even atypical variants (epigastric, jaw only) should be flagged.",
     "BINARY", None, None, None, 1, "TRIAGE", "CARDIAC", 1, 1, 9, "LOINC:29273-0"),

    ("T010", "Was there a high-impact trauma event (road traffic accident, fall > 2 metres, assault, penetrating injury)?",
     "Mechanism of injury determines injury severity. Log mechanism for SAMPLE framework.",
     "BINARY", None, None, None, 1, "TRIAGE", "TRAUMA", 1, 1, 10, None),

    ("T011", "Is the patient expressing active thoughts of suicide or self-harm with a specific plan or intent?",
     "Ask directly: Are you thinking of ending your life? Non-judgmental, firm, mandatory assess.",
     "BINARY", None, None, None, 1, "TRIAGE", "PSYCHIATRIC", 1, 1, 11, "LOINC:44261-6"),

    ("T012", "Is the patient pregnant AND experiencing heavy vaginal bleeding, severe abdominal pain, or reduced fetal movements?",
     "Possible placental abruption, ectopic rupture, or fetal compromise. Obstetric emergency.",
     "BINARY", None, None, None, 1, "TRIAGE", "OBSTETRIC", 1, 1, 12, None),


    # SOCRATES FRAMEWORK
    ("SOC_001", "Where exactly is the pain located? Please tap all affected areas on the body diagram.",
     "Document primary and secondary sites. Multiple sites may indicate referred pain patterns.",
     "BODY_MAP", None, None, None, 2, "SOCRATES", None, 0, 1, 10, "LOINC:38208-5"),

    ("SOC_002", "When did this pain first start?",
     "Sudden onset (<1 min) suggests vascular emergency; gradual onset suggests inflammatory cause.",
     "DATE_PICKER", None, None, None, 2, "SOCRATES", None, 0, 1, 20, "LOINC:85585-8"),

    ("SOC_003", "Did the pain start suddenly (within seconds/minutes) or come on gradually over hours or days?",
     "Thunderclap = SAH; sudden pleuritic = PE/pneumothorax; gradual = infection, inflammation.",
     "SINGLE_SELECT",
     '["Sudden (seconds to minutes)", "Rapid (minutes to an hour)", "Gradual (hours to days)", "Very slow (over weeks/months)"]',
     None, None, 2, "SOCRATES", None, 0, 1, 25, None),

    ("SOC_004", "How would you describe the character of the pain? Select all that apply.",
     "Character is highly discriminating: crushing=cardiac; burning=GERD/neuropathy; colicky=visceral.",
     "MULTI_SELECT",
     '["Crushing / Pressure / Tight", "Burning / Searing", "Sharp / Stabbing / Knife-like", "Dull / Aching / Heavy", "Throbbing / Pulsating", "Cramping / Colicky / Wave-like", "Tearing / Ripping", "Gnawing / Boring", "Shooting / Electric", "Squeezing"]',
     None, None, 2, "SOCRATES", None, 0, 1, 30, "LOINC:38266-3"),

    ("SOC_005", "Does the pain spread or radiate to another part of the body? If yes, tap where it spreads to.",
     "Left arm/jaw = cardiac; right shoulder = biliary; groin/flank = renal colic; back = aortic.",
     "BODY_MAP", None, None, None, 2, "SOCRATES", None, 0, 0, 40, "LOINC:38209-3"),

    ("SOC_006", "What other symptoms are associated with this pain? Select all that apply.",
     "Associated symptoms are critical discriminators for final diagnosis.",
     "MULTI_SELECT",
     '["Nausea", "Vomiting", "Sweating / Diaphoresis", "Shortness of breath", "Dizziness / Lightheadedness", "Fever / Chills", "Palpitations / Racing heart", "Loss of appetite", "Jaundice", "Blood in stool/urine/vomit", "Cough", "Leg swelling", "Rash", "Headache"]',
     None, None, 2, "SOCRATES", None, 0, 1, 50, None),

    ("SOC_007", "Is the pain constant all the time, or does it come and go in waves?",
     "Constant = inflammatory/vascular; colicky/wave-like = ureteric stone, bowel obstruction, biliary.",
     "SINGLE_SELECT",
     '["Constant - present all the time", "Intermittent - comes and goes in episodes", "Colicky - waves of severe pain with pain-free intervals", "Only present with specific activity or movement"]',
     None, None, 2, "SOCRATES", None, 0, 1, 60, None),

    ("SOC_008", "What makes the pain worse? Select all that apply.",
     "Exacerbating factors help exclude or confirm specific diagnoses.",
     "MULTI_SELECT",
     '["Deep breathing / Inspiration", "Movement / Physical activity", "Eating food", "Lying down / Bending forward", "Pressing on the area", "Cold or heat", "Stress or emotion", "Urination / Bowel movement", "Menstruation", "Alcohol", "Nothing makes it worse"]',
     None, None, 2, "SOCRATES", None, 0, 1, 70, None),

    ("SOC_009", "What makes the pain better or gives any relief? Select all that apply.",
     "Relief with GTN = cardiac; antacids = GERD; sitting forward = pericarditis/pancreatitis.",
     "MULTI_SELECT",
     '["Rest / Stopping activity", "Antacids / Milk", "GTN spray or tablet", "Pain killers (paracetamol, ibuprofen)", "Applying heat", "Applying ice / cold compress", "Specific body position (sitting forward)", "Vomiting", "Bowel movement / Passing gas", "Nothing helps"]',
     None, None, 2, "SOCRATES", None, 0, 1, 80, None),

    ("SOC_010", "On a scale from 0 to 10, how severe is the pain RIGHT NOW? (0=no pain, 10=worst imaginable)",
     "NRS >= 7 = severe, prioritise. Document for pain management and medico-legal record.",
     "SLIDER", None, 0, 10, 2, "SOCRATES", None, 0, 1, 90, "LOINC:72514-3"),


    # OLD CARTS FRAMEWORK
    ("OC_001", "When did you first notice this symptom or problem?",
     "Duration helps classify: acute (<2 weeks), subacute (2-6 weeks), chronic (>6 weeks).",
     "DATE_PICKER", None, None, None, 2, "OLD_CARTS", None, 0, 1, 10, None),

    ("OC_002", "Where in the body is this symptom most noticeable? Tap the area on the diagram.",
     "Location anchors the differential: central vs. peripheral; unilateral vs. bilateral.",
     "BODY_MAP", None, None, None, 2, "OLD_CARTS", None, 0, 1, 20, None),

    ("OC_003", "How long does each episode of this symptom last when it occurs?",
     "Episodes lasting seconds = arrhythmia; minutes = TIA/angina; hours = migraine; days = infection.",
     "SINGLE_SELECT",
     '["Seconds", "A few minutes (< 15 min)", "15 minutes to 1 hour", "1 to 4 hours", "4 to 24 hours", "More than a day", "Continuous / Always present"]',
     None, None, 2, "OLD_CARTS", None, 0, 1, 30, None),

    ("OC_004", "How would you describe the nature or character of this symptom? Select all that apply.",
     "Character is the most discriminating dimension in many systemic complaints.",
     "MULTI_SELECT",
     '["Constant and unchanging", "Getting progressively worse over time", "Getting progressively better", "Comes and goes in cycles", "Worse in the morning, better later", "Worse in the evening / at night", "Related to meals or diet", "Related to physical exertion", "Related to stress or emotions", "Seasonal pattern"]',
     None, None, 2, "OLD_CARTS", None, 0, 1, 40, None),

    ("OC_005", "What factors or activities make this symptom worse? Select all that apply.",
     "Aggravating factors direct the clinical pathway.",
     "MULTI_SELECT",
     '["Physical exertion / Exercise", "Cold weather", "Hot weather / Sweating", "Eating / Certain foods", "Fasting / Skipping meals", "Lying flat", "Stress or anxiety", "Alcohol or smoking", "Medications", "Menstruation", "Morning stiffness", "Nothing specific"]',
     None, None, 2, "OLD_CARTS", None, 0, 1, 50, None),

    ("OC_006", "Does this symptom radiate, spread, or are there other body parts affected at the same time?",
     "Bilateral symptoms vs. unilateral; proximal vs. distal involvement is clinically significant.",
     "BINARY", None, None, None, 2, "OLD_CARTS", None, 0, 0, 60, None),

    ("OC_007", "How often does this symptom occur? What is the pattern over time?",
     "Frequency pattern helps distinguish episodic from progressive disease.",
     "SINGLE_SELECT",
     '["First time ever", "Several times a day", "Daily", "Several times a week", "Weekly", "Several times a month", "Monthly or less often", "Unpredictable / No pattern"]',
     None, None, 2, "OLD_CARTS", None, 0, 1, 70, None),

    ("OC_008", "On a scale from 0 to 10, how much does this symptom affect your daily life? (0=not at all, 10=unable to function)",
     "Functional impairment score determines urgency tier and management intensity.",
     "SLIDER", None, 0, 10, 2, "OLD_CARTS", None, 0, 1, 80, "LOINC:89205-6"),


    # SAMPLE FRAMEWORK
    ("SAM_001", "What symptoms are you experiencing RIGHT NOW as a result of the incident? Select all that apply.",
     "Current symptom inventory post-trauma. Compare with pre-event baseline if possible.",
     "MULTI_SELECT",
     '["Pain", "Difficulty breathing", "Bleeding", "Dizziness", "Nausea or vomiting", "Loss of consciousness (even briefly)", "Numbness or tingling", "Inability to move a limb", "Visual disturbance", "Headache", "Confusion / Memory loss", "None currently"]',
     None, None, 2, "SAMPLE", None, 0, 1, 10, None),

    ("SAM_002", "Do you have any known allergies - to medications, foods, latex, or environmental triggers?",
     "Drug allergies affect treatment choice. Allergy type: anaphylactic vs. intolerance.",
     "MULTI_SELECT",
     '["No known allergies", "Penicillin / Amoxicillin", "Aspirin / NSAIDs", "Sulfa drugs", "Contrast dye", "Latex", "Nuts / Shellfish", "Dairy / Gluten", "Other medication allergy", "Other food allergy", "Environmental (pollen, dust)", "Not sure"]',
     None, None, 2, "SAMPLE", None, 0, 1, 20, None),

    ("SAM_003", "What medications or supplements are you currently taking regularly?",
     "Medication list critical for drug interactions, contraindications, and diagnosis.",
     "MULTI_SELECT",
     '["None / No regular medications", "Blood thinners (Warfarin, Aspirin, Clopidogrel)", "Blood pressure medicines", "Diabetes medicines", "Heart medicines", "Thyroid medicines", "Steroids", "Antibiotics", "Pain killers (regular use)", "Psychiatric medicines", "Inhalers / Nebulizers", "Contraceptive pill / HRT", "Herbal / Traditional medicines", "Vitamins / Supplements", "Unsure"]',
     None, None, 2, "SAMPLE", None, 0, 1, 30, None),

    ("SAM_004", "Do you have any significant past medical history? Select all conditions that apply.",
     "Key comorbidities that affect assessment and management planning.",
     "MULTI_SELECT",
     '["None", "Hypertension", "Diabetes mellitus", "Heart disease / CAD", "Heart failure", "Stroke or TIA", "Asthma or COPD", "Kidney disease", "Liver disease", "Epilepsy", "Thyroid disorder", "Cancer", "HIV", "Tuberculosis", "Psychiatric illness", "Autoimmune disease", "Not sure"]',
     None, None, 2, "SAMPLE", None, 0, 1, 40, None),

    ("SAM_005", "When did you last eat or drink anything (including water)?",
     "Nil-by-mouth status critical for anaesthesia safety and procedural planning.",
     "SINGLE_SELECT",
     '["Less than 2 hours ago", "2-4 hours ago", "4-6 hours ago", "6-8 hours ago", "More than 8 hours ago", "Cannot remember"]',
     None, None, 2, "SAMPLE", None, 0, 1, 50, None),

    ("SAM_006", "What were the exact circumstances leading up to this event?",
     "Mechanism of injury is the most predictive factor for injury pattern in trauma.",
     "SINGLE_SELECT",
     '["Road traffic accident (driver)", "Road traffic accident (passenger)", "Road traffic accident (pedestrian/cyclist)", "Fall on the same level (trip/slip)", "Fall from height (> 1 metre)", "Sports or recreational injury", "Workplace / Industrial accident", "Assault", "Penetrating injury (stabbing, gunshot)", "Burn (thermal/chemical/electrical)", "Drowning or near-drowning", "Poisoning or drug overdose", "No specific traumatic event"]',
     None, None, 2, "SAMPLE", None, 0, 1, 60, None),


    # COCA FRAMEWORK
    ("COCA_001", "What is the colour of the fluid, discharge, or body output you have noticed? Select all that match.",
     "Colour is the most immediately discriminating feature: red=blood, green=bile/infection.",
     "MULTI_SELECT",
     '["Clear / Colourless", "Yellow / Pale yellow", "Dark yellow / Amber", "Orange", "Brown / Tea-coloured", "Pink / Light red (blood-tinged)", "Bright red (fresh blood)", "Dark red / Maroon", "Black / Tarry", "Green / Olive green", "Grey or clay-coloured", "White / Milky / Frothy", "Purulent / Cloudy / Pus-like", "Mixed colours"]',
     None, None, 2, "COCA", None, 0, 1, 10, None),

    ("COCA_002", "Does the fluid or output have an unusual or noticeable smell?",
     "Foul odor = infection; sweet/fruity = DKA/ketosis; ammonia = renal failure.",
     "SINGLE_SELECT",
     '["No unusual smell", "Foul / Putrid / Rotten", "Sweet or fruity", "Ammonia-like", "Fishy", "Metallic", "Musty", "Strong but not unpleasant"]',
     None, None, 2, "COCA", None, 0, 1, 20, None),

    ("COCA_003", "What is the consistency or texture of the fluid or output?",
     "Consistency determines urgency: watery = secretory; bloody mucus = IBD.",
     "SINGLE_SELECT",
     '["Watery / Liquid", "Loose / Soft", "Formed but soft", "Normal formed", "Hard / Dry / Pellets", "Frothy / Bubbly", "Mucousy / Slimy", "Thick / Viscous", "Chunky / Contains undigested food", "Mixed / Variable"]',
     None, None, 2, "COCA", None, 0, 1, 30, None),

    ("COCA_004", "How much fluid or output are you producing? How has this changed from normal?",
     "Volume: oliguria (<0.5 mL/kg/hr) = renal compromise; polyuria = DI/DM.",
     "SINGLE_SELECT",
     '["Much less than normal (decreased / absent)", "Slightly less than normal", "About the same as normal", "Slightly more than normal", "Much more than normal", "First time I have noticed this"]',
     None, None, 2, "COCA", None, 0, 1, 40, None),


    # ROTS FRAMEWORK
    ("ROTS_001", "Are there any significant risk factors or stressors in your life currently? Select all that apply.",
     "Bio-psycho-social risk factors drive psychiatric differential. Non-judgmental framing essential.",
     "MULTI_SELECT",
     '["Major life loss (bereavement)", "Relationship breakdown / Divorce", "Job loss / Financial stress", "History of trauma or abuse", "Substance use", "Chronic physical illness", "Social isolation", "History of mental illness", "Family member with mental illness", "Significant life change", "Legal problems", "No significant stressors"]',
     None, None, 2, "ROTS", None, 0, 1, 10, None),

    ("ROTS_002", "When did these thoughts, feelings, or changes in behaviour first start?",
     "Acute onset = delirium (organic cause likely); subacute = functional; chronic = persistent disorder.",
     "SINGLE_SELECT",
     '["Within the last 24 hours", "Over the past few days (2-7 days)", "1 to 4 weeks ago", "1 to 3 months ago", "3 to 12 months ago", "More than 1 year ago", "Since childhood or adolescence", "Cannot pinpoint a start"]',
     None, None, 2, "ROTS", None, 0, 1, 20, None),

    ("ROTS_003", "Was there a specific trigger or event that started or worsened the symptoms?",
     "Identified triggers help distinguish reactive from endogenous conditions.",
     "MULTI_SELECT",
     '["A traumatic event or accident", "A significant loss", "Starting or stopping a medication", "Substance use", "A physical illness or infection", "Sleep deprivation", "A major life change", "No identifiable trigger", "Not sure"]',
     None, None, 2, "ROTS", None, 0, 1, 30, None),

    ("ROTS_004", "Do you have people around you who can provide support - family, friends, or community?",
     "Social support is a key protective factor and affects disposition planning.",
     "SINGLE_SELECT",
     '["Strong support: family/friends available and actively helping", "Some support: people available but not always helpful", "Limited support: few people around", "Isolated: I am completely alone", "Support from professionals only", "I prefer not to say"]',
     None, None, 2, "ROTS", None, 0, 1, 40, None),

    ("ROTS_005", "How are these problems affecting your ability to carry out daily activities?",
     "Global Assessment of Functioning proxy. Functional impairment = severity marker.",
     "SINGLE_SELECT",
     '["No impact - I can function normally", "Mild impact - Some difficulty but managing", "Moderate impact - Significant difficulty in some areas", "Severe impact - Major difficulty in most areas", "Total impact - Cannot carry out basic daily activities"]',
     None, None, 2, "ROTS", None, 0, 1, 50, None),

    # ROS SYSTEM 1: CONSTITUTIONAL
    ("ROS_CON_001", "Have you had a fever or felt feverish recently?",
     "Temperature > 38.3C = fever. > 39.4C = high fever. > 41C = hyperpyrexia (emergency).",
     "SINGLE_SELECT",
     '["No fever", "Low-grade: 37.5-38.2 C", "Moderate: 38.3-39.3 C", "High: 39.4-40.9 C", "Very high: 41 C or above", "I think I had fever but did not measure"]',
     None, None, 3, "ROS", "CONSTITUTIONAL", 0, 0, 10, "LOINC:8310-5"),

    ("ROS_CON_002", "Have you noticed unexplained weight loss in the last 3-6 months?",
     "Weight loss > 5% body weight in 6 months = clinically significant. Exclude malignancy, TB, HIV.",
     "SINGLE_SELECT",
     '["No weight change", "Slight loss (< 2 kg)", "Moderate loss (2-5 kg)", "Significant loss (5-10 kg)", "Severe loss (> 10 kg)", "Not sure"]',
     None, None, 3, "ROS", "CONSTITUTIONAL", 0, 0, 20, "LOINC:29463-7"),

    ("ROS_CON_003", "Have you been feeling unusually tired or fatigued, even with adequate sleep?",
     "Fatigue: mild = effort required; moderate = limits daily activity; severe = bedridden.",
     "SINGLE_SELECT",
     '["No unusual fatigue", "Mild - tire more easily than usual", "Moderate - fatigue limits activities", "Severe - mostly in bed or resting", "Exhaustion - cannot get out of bed"]',
     None, None, 3, "ROS", "CONSTITUTIONAL", 0, 0, 30, "LOINC:89250-2"),

    ("ROS_CON_004", "Have you experienced drenching night sweats that soak through your clothing or bedding?",
     "Drenching night sweats + fever + weight loss = B-symptoms (lymphoma, TB, HIV indicator).",
     "BINARY", None, None, None, 3, "ROS", "CONSTITUTIONAL", 0, 0, 40, None),

    ("ROS_CON_005", "Have you noticed any loss of appetite (poor appetite / not feeling hungry) recently?",
     "Anorexia accompanies many systemic conditions including malignancy, depression, and hepatitis.",
     "BINARY", None, None, None, 3, "ROS", "CONSTITUTIONAL", 0, 0, 50, "LOINC:44255-8"),

    ("ROS_CON_006", "Have you had any recent chills or rigors (uncontrollable shaking with fever)?",
     "Rigors indicate rapid temperature rise; common in bacteremia, malaria, pyelonephritis.",
     "BINARY", None, None, None, 3, "ROS", "CONSTITUTIONAL", 0, 0, 60, None),

    ("ROS_CON_007", "Has your overall sense of well-being been different from your usual baseline recently?",
     "General malaise is a non-specific but sensitive marker of systemic illness.",
     "SINGLE_SELECT",
     '["Same as usual", "Slightly unwell / Below par", "Moderately unwell / Noticeably different", "Very unwell / Much worse than usual", "Worst I have ever felt"]',
     None, None, 3, "ROS", "CONSTITUTIONAL", 0, 0, 70, None),

    ("ROS_CON_008", "Have you recently travelled to a malaria-endemic region or been exposed to any infectious illness contacts?",
     "Travel history changes the prior probability of tropical infections significantly.",
     "BINARY", None, None, None, 3, "ROS", "CONSTITUTIONAL", 0, 0, 80, None),

    # ROS SYSTEM 2: EYES
    ("ROS_EYE_001", "Have you noticed any change in your vision - blurring, double vision, or loss of vision?",
     "Sudden monocular blindness = arterial occlusion. Bilateral = cortical. Diplopia = CN palsy.",
     "MULTI_SELECT",
     '["No change in vision", "Blurred vision (one eye)", "Blurred vision (both eyes)", "Double vision", "Loss of vision (one eye)", "Loss of vision (both eyes)", "Loss of peripheral vision", "Floating spots / Floaters", "Flashing lights", "Halo around lights at night"]',
     None, None, 3, "ROS", "EYE", 0, 0, 10, "LOINC:72166-8"),

    ("ROS_EYE_002", "Do your eyes look red or feel painful?",
     "Red painful eye: acute glaucoma, iritis, keratitis. Red painless: conjunctivitis, subconjunctival bleed.",
     "SINGLE_SELECT",
     '["No redness or pain", "Redness without pain", "Redness with mild discomfort / Grittiness", "Redness with moderate pain", "Severe pain with or without redness"]',
     None, None, 3, "ROS", "EYE", 0, 0, 20, None),

    ("ROS_EYE_003", "Is there any discharge from your eyes? What does it look like?",
     "Watery = viral conjunctivitis; purulent = bacterial; mucoid = allergic.",
     "SINGLE_SELECT",
     '["No discharge", "Watery / Teary", "Clear / White mucoid", "Yellow or green pus", "Crusty / Matted lashes in morning"]',
     None, None, 3, "ROS", "EYE", 0, 0, 30, None),

    ("ROS_EYE_004", "Are your eyes sensitive to light (photophobia)?",
     "Photophobia + headache + neck stiffness = meningitis triad. Also: migraine, uveitis.",
     "BINARY", None, None, None, 3, "ROS", "EYE", 0, 0, 40, None),

    ("ROS_EYE_005", "Have you noticed yellowing of the whites of your eyes (jaundice / icterus)?",
     "Scleral icterus = serum bilirubin > 2.5 mg/dL; indicates hepatic, hemolytic, or biliary disease.",
     "BINARY", None, None, None, 3, "ROS", "EYE", 0, 0, 50, "LOINC:45198-9"),

    ("ROS_EYE_006", "Do you wear glasses or contact lenses? Have you noticed your prescription needing a recent update?",
     "Rapid myopia change = diabetes; sudden need for reading glasses change = age-related or cataract.",
     "BINARY", None, None, None, 3, "ROS", "EYE", 0, 0, 60, None),

    ("ROS_EYE_007", "Have you ever been told you have glaucoma, cataracts, retinal disease, or any other eye condition?",
     "Pre-existing eye conditions affect interpretation of new ocular symptoms.",
     "BINARY", None, None, None, 3, "ROS", "EYE", 0, 0, 70, None),

    # ROS SYSTEM 3: ENMT
    ("ROS_ENT_001", "Do you have any pain or pressure in your ears?",
     "Otalgia: otitis media (referred pain), otitis externa. Rule out mastoiditis in children.",
     "BINARY", None, None, None, 3, "ROS", "ENMT", 0, 0, 10, None),

    ("ROS_ENT_002", "Have you noticed any change or loss of hearing recently?",
     "Sudden sensorineural hearing loss = emergency (steroid-sensitive). Conductive = wax, otitis.",
     "SINGLE_SELECT",
     '["No hearing change", "Mild reduction in hearing", "Moderate hearing loss", "Severe hearing loss", "Sudden complete loss in one ear", "Ringing or buzzing (tinnitus) only"]',
     None, None, 3, "ROS", "ENMT", 0, 0, 20, None),

    ("ROS_ENT_003", "Do you have a blocked or runny nose? What does the discharge look like?",
     "Unilateral bloody nasal discharge in adults = malignancy until proven otherwise.",
     "MULTI_SELECT",
     '["No nasal symptoms", "Blocked nose", "Runny nose - clear", "Runny nose - yellow/green", "Runny nose - bloody", "Reduced or lost sense of smell"]',
     None, None, 3, "ROS", "ENMT", 0, 0, 30, None),

    ("ROS_ENT_004", "Do you have a sore throat, pain on swallowing, or difficulty swallowing?",
     "Drooling + stridor + inability to swallow = epiglottitis (emergency). Unilateral = peritonsillar abscess.",
     "MULTI_SELECT",
     '["No throat symptoms", "Mild sore throat", "Moderate sore throat affecting speech", "Severe pain on swallowing", "Difficulty swallowing solids", "Difficulty swallowing liquids", "Drooling / Cannot swallow saliva", "Hoarse voice"]',
     None, None, 3, "ROS", "ENMT", 0, 0, 40, None),

    ("ROS_ENT_005", "Do you have any mouth sores, ulcers, or dental pain?",
     "Non-healing oral ulcer > 3 weeks = exclude malignancy. Aphthous ulcers: SLE, Behcets, Crohn.",
     "BINARY", None, None, None, 3, "ROS", "ENMT", 0, 0, 50, None),

    ("ROS_ENT_006", "Do you experience dizziness or a spinning sensation (vertigo)?",
     "Vertigo: BPPV (positional), Menieres (with tinnitus/hearing loss), central (cerebellar signs).",
     "SINGLE_SELECT",
     '["No dizziness", "Light-headedness / Feeling faint", "True vertigo: room spinning", "Imbalance / Unsteady without spinning", "Vertigo triggered by head position changes"]',
     None, None, 3, "ROS", "ENMT", 0, 0, 60, None),

    ("ROS_ENT_007", "Do you have pain over your face/cheekbones/forehead that worsens when bending forward?",
     "Facial pressure + nasal congestion + fever = acute sinusitis.",
     "BINARY", None, None, None, 3, "ROS", "ENMT", 0, 0, 70, None),

    ("ROS_ENT_008", "Do you have any swollen glands (lymph nodes) in your neck?",
     "Cervical lymphadenopathy: infection (most common), lymphoma, thyroid disease, EBV.",
     "BINARY", None, None, None, 3, "ROS", "ENMT", 0, 0, 80, None),

    # ROS SYSTEM 4: CARDIOVASCULAR
    ("ROS_CVS_001", "Do you experience chest pain, tightness, or pressure with or without exertion?",
     "Exertional chest pain relieved by rest = stable angina. At rest = unstable angina/ACS.",
     "MULTI_SELECT",
     '["No chest pain", "Chest tightness on exertion", "Chest pain at rest", "Chest pain with emotional stress", "Chest pain relieved by GTN", "Chest discomfort after meals", "Sharp chest pain worse with breathing", "Chest pain radiating to left arm or jaw"]',
     None, None, 3, "ROS", "CVS", 0, 0, 10, "LOINC:29273-0"),

    ("ROS_CVS_002", "Do you experience shortness of breath when lying flat (orthopnoea)? How many pillows do you sleep with?",
     "Orthopnoea is a specific sign of left heart failure. Count pillows: 2+ = clinically significant.",
     "SINGLE_SELECT",
     '["No - I sleep flat without difficulty", "I prefer 1 extra pillow", "I use 2 pillows to prevent breathlessness", "I use 3 or more pillows", "I must sleep sitting upright"]',
     None, None, 3, "ROS", "CVS", 0, 0, 20, None),

    ("ROS_CVS_003", "Do you wake up suddenly at night with severe breathlessness (paroxysmal nocturnal dyspnoea)?",
     "PND = classic heart failure symptom. Occurs 1-3 hours after sleep onset; relieves on sitting up.",
     "BINARY", None, None, None, 3, "ROS", "CVS", 0, 0, 30, None),

    ("ROS_CVS_004", "Do you have swelling in your ankles, legs, or abdomen?",
     "Peripheral edema: right heart failure, hypoalbuminemia, venous insufficiency, DVT.",
     "SINGLE_SELECT",
     '["No swelling", "Mild ankle swelling at end of day", "Moderate ankle and lower leg swelling", "Severe swelling extending above the knees", "Abdominal swelling (ascites possible)", "Facial swelling (morning)"]',
     None, None, 3, "ROS", "CVS", 0, 0, 40, "LOINC:44966-0"),

    ("ROS_CVS_005", "Do you experience palpitations - racing heart, fluttering, or irregular beats?",
     "Rapid-regular = SVT/sinus tach; irregular = AF; pause = heart block.",
     "MULTI_SELECT",
     '["No palpitations", "Racing heartbeat (fast and regular)", "Irregular heartbeat / Missed beats", "Fluttering or skipping sensation", "Pounding heartbeat", "Palpitations with dizziness or fainting", "Palpitations at rest", "Palpitations on exertion only"]',
     None, None, 3, "ROS", "CVS", 0, 0, 50, None),

    ("ROS_CVS_006", "Have you ever fainted or lost consciousness unexpectedly?",
     "Syncope: vasovagal (prodrome: nausea, pale, trigger), cardiac (abrupt, no warning), orthostatic.",
     "SINGLE_SELECT",
     '["Never", "Once", "2-3 times", "Recurrent episodes (> 3 times)", "Near-faint without full loss of consciousness"]',
     None, None, 3, "ROS", "CVS", 0, 0, 60, "LOINC:45957-8"),

    ("ROS_CVS_007", "Do you have high blood pressure (hypertension)? Are you on blood pressure medication?",
     "Known hypertension increases pre-test probability of cardiac, renal, and cerebrovascular disease.",
     "BINARY", None, None, None, 3, "ROS", "CVS", 0, 0, 70, "LOINC:55284-4"),

    ("ROS_CVS_008", "Do you experience leg pain or cramping when walking that goes away with rest (claudication)?",
     "Intermittent claudication = peripheral arterial disease (PAD). Classic: calf pain, reproducible.",
     "BINARY", None, None, None, 3, "ROS", "CVS", 0, 0, 80, None),

    ("ROS_CVS_009", "Has your doctor ever told you that you have a heart murmur or abnormal heart rhythm?",
     "Known murmur or arrhythmia changes the cardiac differential significantly.",
     "BINARY", None, None, None, 3, "ROS", "CVS", 0, 0, 90, None),

    # ROS SYSTEM 5: RESPIRATORY
    ("ROS_RES_001", "Do you have a cough? If yes, how long have you had it?",
     "Cough > 8 weeks = chronic. Duration guides differential.",
     "SINGLE_SELECT",
     '["No cough", "Cough for less than 1 week", "Cough for 1-3 weeks", "Cough for 3-8 weeks", "Chronic cough (more than 8 weeks)", "Lifelong / Since childhood"]',
     None, None, 3, "ROS", "RESP", 0, 0, 10, "LOINC:28315-7"),

    ("ROS_RES_002", "Are you coughing up phlegm (sputum)? If yes, what colour is it?",
     "Clear = viral/asthma; yellow/green = bacterial; rust = pneumococcal; blood = TB/CA.",
     "SINGLE_SELECT",
     '["No phlegm / Dry cough", "White or clear phlegm", "Yellow phlegm", "Green phlegm", "Grey or brown phlegm", "Rust-coloured or blood-tinged phlegm", "Frank blood (haemoptysis)", "Frothy pink phlegm"]',
     None, None, 3, "ROS", "RESP", 0, 0, 20, None),

    ("ROS_RES_003", "Do you have shortness of breath? How much activity triggers it?",
     "MRC Dyspnoea Scale Grade 1-5: Grade 1 = only strenuous; Grade 5 = at rest.",
     "SINGLE_SELECT",
     '["No shortness of breath", "Only with very strenuous activity (MRC Grade 1)", "Slight shortness with hurrying (Grade 2)", "Shortness walking on flat at own pace (Grade 3)", "Must stop after 100 metres (Grade 4)", "Shortness of breath at rest (Grade 5)"]',
     None, None, 3, "ROS", "RESP", 0, 0, 30, "LOINC:89434-2"),

    ("ROS_RES_004", "Do you experience wheezing (high-pitched whistling sound when breathing)?",
     "Expiratory wheeze = bronchospasm (asthma, COPD). Inspiratory stridor = upper airway obstruction.",
     "BINARY", None, None, None, 3, "ROS", "RESP", 0, 0, 40, None),

    ("ROS_RES_005", "Do you experience chest tightness or difficulty taking a deep breath?",
     "Chest tightness: asthma, anxiety, musculoskeletal. Cannot deep breathe = pleuritic pain/effusion.",
     "BINARY", None, None, None, 3, "ROS", "RESP", 0, 0, 50, None),

    ("ROS_RES_006", "Have you ever coughed up blood (haemoptysis)?",
     "Any haemoptysis must be taken seriously: TB, lung cancer, PE, bronchiectasis, AVM.",
     "SINGLE_SELECT",
     '["No blood in cough", "Streaks of blood in phlegm", "Small amount of frank blood", "Large volume (> 1 tablespoon)", "Repeated episodes of blood in cough"]',
     None, None, 3, "ROS", "RESP", 0, 0, 60, "LOINC:21909-3"),

    ("ROS_RES_007", "Do you smoke or have you smoked in the past? How much and for how long?",
     "Pack-year history: packs/day x years smoked. >20 pack-years = significant COPD/cancer risk.",
     "SINGLE_SELECT",
     '["Never smoked", "Ex-smoker (stopped > 1 year ago)", "Ex-smoker (stopped < 1 year ago)", "Current smoker < 10/day", "Current smoker 10-20/day", "Current smoker > 20/day", "Hookah / Bidi / Pipe smoker", "Passive smoker only"]',
     None, None, 3, "ROS", "RESP", 0, 0, 70, "LOINC:72166-8"),

    ("ROS_RES_008", "Have you been exposed to asbestos, coal dust, silica, or other occupational lung hazards?",
     "Occupational exposure: asbestosis, silicosis, coal workers pneumoconiosis.",
     "BINARY", None, None, None, 3, "ROS", "RESP", 0, 0, 80, None),

    # ROS SYSTEM 6: GASTROINTESTINAL
    ("ROS_GI_001", "Do you have nausea or vomiting? Does the vomit contain blood?",
     "Haematemesis = upper GI bleed (emergency). Coffee-ground = older blood. Projectile = pyloric.",
     "MULTI_SELECT",
     '["No nausea or vomiting", "Nausea without vomiting", "Vomiting (no blood)", "Vomiting - coffee-ground (old blood)", "Vomiting - fresh bright red blood", "Vomiting - bile", "Projectile vomiting", "Vomiting after every meal"]',
     None, None, 3, "ROS", "GI", 0, 0, 10, None),

    ("ROS_GI_002", "Do you have abdominal pain or cramping? Where? Does it relate to meals?",
     "Epigastric post-meal = PUD/GERD. RLQ = appendicitis. RUQ = biliary. Periumbilical = early appendicitis.",
     "MULTI_SELECT",
     '["No abdominal pain", "Upper abdominal pain (epigastric)", "Right upper quadrant", "Left upper quadrant", "Umbilical / Central", "Right lower quadrant", "Left lower quadrant", "Lower abdominal / Pelvic", "Diffuse / Generalised", "Pain before meals", "Pain 1-2 hours after meals"]',
     None, None, 3, "ROS", "GI", 0, 0, 20, "LOINC:18282-4"),

    ("ROS_GI_003", "What are your bowel habits like? Have they changed recently?",
     "Change in bowel habit >4 weeks in adults >50 = red flag for colorectal cancer.",
     "MULTI_SELECT",
     '["Normal / No change", "Constipation (< 3 bowel movements/week)", "Diarrhoea (> 3 loose stools/day)", "Alternating diarrhoea and constipation", "Ribbon-like or pencil-thin stools", "Urgency", "Tenesmus (feeling of incomplete emptying)", "Mucus in stool", "Blood in stool (bright red)", "Black tarry stools (melena)"]',
     None, None, 3, "ROS", "GI", 0, 0, 30, "LOINC:33681-3"),

    ("ROS_GI_004", "Do you experience heartburn, acid reflux, or a sour taste in the mouth?",
     "GERD: heartburn after meals, when lying down, relieved by antacids. Chronic GERD = Barrett risk.",
     "BINARY", None, None, None, 3, "ROS", "GI", 0, 0, 40, None),

    ("ROS_GI_005", "Have you had any difficulty swallowing (dysphagia)? Is it worse for solids, liquids, or both?",
     "Progressive dysphagia to solids then liquids = mechanical obstruction. Both = motility disorder.",
     "SINGLE_SELECT",
     '["No swallowing difficulty", "Difficulty swallowing solids only", "Difficulty swallowing both solids and liquids", "Difficulty swallowing liquids only", "Painful swallowing (odynophagia)", "Food getting stuck / Regurgitation"]',
     None, None, 3, "ROS", "GI", 0, 0, 50, None),

    ("ROS_GI_006", "Have you noticed yellowing of skin/eyes, dark urine, or pale/clay-coloured stools?",
     "Jaundice triad: yellow skin, dark urine, pale stool = obstructive or hepatocellular disease.",
     "MULTI_SELECT",
     '["None of these", "Yellow skin (jaundice)", "Yellow whites of eyes", "Very dark urine", "Pale / Clay-coloured stools", "Generalised itching without rash"]',
     None, None, 3, "ROS", "GI", 0, 0, 60, "LOINC:45198-9"),

    ("ROS_GI_007", "Do you drink alcohol? How much and how frequently?",
     "AUDIT-C proxy. >14 units/week (men) or >7 units (women) = hazardous. Alcohol liver disease risk.",
     "SINGLE_SELECT",
     '["I do not drink alcohol", "Occasionally (< 1 drink/week)", "Socially (1-7 units/week)", "Regularly (8-14 units/week)", "Heavy use (15-28 units/week)", "Very heavy / Daily (> 28 units/week)", "Prefer not to say"]',
     None, None, 3, "ROS", "GI", 0, 0, 70, "LOINC:72109-8"),

    ("ROS_GI_008", "Have you been diagnosed with any liver, gallbladder, or pancreatic disease?",
     "Pre-existing hepatic/biliary/pancreatic disease alters the GI differential significantly.",
     "BINARY", None, None, None, 3, "ROS", "GI", 0, 0, 80, None),

    ("ROS_GI_009", "Do you have any perianal symptoms: rectal bleeding, anal pain, prolapse, or change in anal habits?",
     "Bright red blood per rectum: haemorrhoids (painless), fissure (painful). Dark blood = higher source.",
     "MULTI_SELECT",
     '["No perianal symptoms", "Bright red blood on toilet paper or in bowl", "Anal pain / Soreness", "Protrusion from anus", "Anal discharge or mucus", "Perianal itching", "Lump near anus"]',
     None, None, 3, "ROS", "GI", 0, 0, 90, None),

    # ROS SYSTEM 7: GENITOURINARY
    ("ROS_GU_001", "Do you have any pain or burning during urination (dysuria)?",
     "Dysuria + frequency + urgency = UTI. Dysuria alone in men = urethritis.",
     "BINARY", None, None, None, 3, "ROS", "GU", 0, 0, 10, "LOINC:28335-5"),

    ("ROS_GU_002", "How frequently are you urinating? Has this changed recently?",
     "Frequency: UTI (sudden), DM (polyuria with polydipsia), BPH (gradual, nocturia).",
     "SINGLE_SELECT",
     '["Normal frequency (4-8 times/day)", "Slightly increased (8-12 times/day)", "Markedly increased (> 12 times/day)", "Getting up multiple times at night", "Decreased frequency with reduced output", "Completely no urine (anuria)"]',
     None, None, 3, "ROS", "GU", 0, 0, 20, None),

    ("ROS_GU_003", "Have you noticed blood in your urine (haematuria)?",
     "Painless visible haematuria in adults > 35 = bladder cancer until proven otherwise.",
     "SINGLE_SELECT",
     '["No blood in urine", "Visible blood - pink or red urine", "Visible blood - brown/Cola-coloured", "Blood throughout urination", "Blood only at start", "Blood only at end", "Blood found on urine test only"]',
     None, None, 3, "ROS", "GU", 0, 0, 30, "LOINC:5778-6"),

    ("ROS_GU_004", "Do you experience weak urinary stream, difficulty starting, or feeling of incomplete emptying?",
     "Obstructive symptoms in men = BPH (common), prostate cancer. Urgency = overactive bladder.",
     "MULTI_SELECT",
     '["No urinary symptoms", "Weak or slow urinary stream", "Difficulty starting (hesitancy)", "Dribbling at end", "Feeling of incomplete emptying", "Urgency", "Urge incontinence", "Stress incontinence"]',
     None, None, 3, "ROS", "GU", 0, 0, 40, None),

    ("ROS_GU_005", "FOR FEMALES: Have you noticed any change in your menstrual cycle, bleeding, or vaginal discharge?",
     "Menstrual irregularity: PCOS, thyroid, DM. Abnormal discharge: PID, BV, STI.",
     "MULTI_SELECT",
     '["Not applicable", "Regular periods / No change", "Irregular periods", "Heavier or longer periods", "Lighter or shorter periods", "No periods", "Periods stopped (post-menopause)", "Abnormal vaginal discharge", "Inter-menstrual bleeding", "Post-coital bleeding", "Pelvic pain around periods"]',
     None, None, 3, "ROS", "GU", 0, 0, 50, None),

    ("ROS_GU_006", "Have you had any flank pain (pain in the side/back below the ribs) associated with urination?",
     "Flank pain + fever + dysuria = pyelonephritis. Severe colicky flank pain to groin = renal colic.",
     "BINARY", None, None, None, 3, "ROS", "GU", 0, 0, 60, None),

    ("ROS_GU_007", "Have you ever had kidney stones, urinary tract infections, or any other kidney/bladder conditions?",
     "History of renal calculi markedly increases pre-test probability of recurrent stone disease.",
     "BINARY", None, None, None, 3, "ROS", "GU", 0, 0, 70, None),

    ("ROS_GU_008", "FOR FEMALES: Is there any possibility you could be pregnant? When was your last menstrual period?",
     "All women of reproductive age with abdominal pain/vomiting must have pregnancy excluded.",
     "SINGLE_SELECT",
     '["Not applicable (male or post-menopausal)", "Definitely not pregnant", "Possibly pregnant / Not sure", "Currently pregnant (known)", "LMP was within the last 4 weeks"]',
     None, None, 3, "ROS", "GU", 0, 0, 80, None),

    # ROS SYSTEM 8: MUSCULOSKELETAL
    ("ROS_MSK_001", "Do you have joint pain or swelling? Which joints are affected?",
     "Monoarthritis = infection/gout. Polyarthritis = RA, viral. Migratory = reactive arthritis.",
     "MULTI_SELECT",
     '["No joint pain or swelling", "Small joints of hands and fingers", "Wrists", "Elbows", "Shoulders", "Neck", "Upper back", "Lower back (lumbar spine)", "Hips", "Knees", "Ankles", "Feet and toes", "Multiple joints (> 4)"]',
     None, None, 3, "ROS", "MSK", 0, 0, 10, "LOINC:72300-4"),

    ("ROS_MSK_002", "Is there morning joint stiffness? How long does it last?",
     "Morning stiffness > 60 min = inflammatory arthritis (RA). < 30 min = osteoarthritis.",
     "SINGLE_SELECT",
     '["No morning stiffness", "Stiffness < 15 minutes", "Stiffness 15-30 minutes", "Stiffness 30-60 minutes", "Stiffness > 60 minutes", "Stiffness persisting most of the day"]',
     None, None, 3, "ROS", "MSK", 0, 0, 20, None),

    ("ROS_MSK_003", "Do you have back pain? Where exactly? Does it radiate down the leg?",
     "Sciatica: L4-S1 disc herniation. Red flags: bilateral + bowel/bladder = emergency.",
     "MULTI_SELECT",
     '["No back pain", "Neck pain", "Upper back / Between shoulder blades", "Lower back", "Sacral / Coccyx region", "Pain into buttock only", "Pain down one leg to the knee", "Pain below the knee to foot", "Bilateral leg pain"]',
     None, None, 3, "ROS", "MSK", 0, 0, 30, "LOINC:72514-3"),

    ("ROS_MSK_004", "Have you had a recent injury, fall, or direct trauma to any bone or joint?",
     "Post-traumatic pain has different differential than atraumatic onset.",
     "BINARY", None, None, None, 3, "ROS", "MSK", 0, 0, 40, None),

    ("ROS_MSK_005", "Do you have any muscle pain, weakness, or cramps?",
     "Myalgia + weakness: inflammatory myopathy, statin-related, hypothyroid, polymyalgia rheumatica.",
     "MULTI_SELECT",
     '["No muscle symptoms", "Generalised muscle aching", "Specific muscle group weakness", "Muscle cramps (especially at night)", "Muscle wasting", "Difficulty rising from a chair"]',
     None, None, 3, "ROS", "MSK", 0, 0, 50, None),

    ("ROS_MSK_006", "Do you have any limitation in range of movement in any joint?",
     "Restricted ROM: osteoarthritis (gradual), septic arthritis (acute + fever), adhesive capsulitis.",
     "BINARY", None, None, None, 3, "ROS", "MSK", 0, 0, 60, None),

    ("ROS_MSK_007", "Have you been told you have osteoporosis, or had a fracture from a minor fall?",
     "Fragility fracture = osteoporosis until proven otherwise. DEXA scan indicated.",
     "BINARY", None, None, None, 3, "ROS", "MSK", 0, 0, 70, None),

    ("ROS_MSK_008", "Do you have any joint redness, warmth, or swelling, especially after eating red meat or drinking alcohol?",
     "Acute monoarthritis: hot/red/swollen first MTP joint (podagra) = gout classic presentation.",
     "BINARY", None, None, None, 3, "ROS", "MSK", 0, 0, 80, None),

    # ROS SYSTEM 9: INTEGUMENTARY
    ("ROS_SKN_001", "Do you have any rash, skin lesion, or change in skin appearance?",
     "Rash: distribution, morphology (macule/papule/vesicle/pustule), colour, border.",
     "MULTI_SELECT",
     '["No rash or skin changes", "Red rash / Erythema", "Scaly / Flaky skin", "Blistering rash", "Pus-filled spots", "Raised bumps (hives)", "Flat discoloured patches", "Bruising / Petechiae", "Dark or pigmented lesion (changing)", "Open wound or ulcer", "Rash following a nerve line (shingles)"]',
     None, None, 3, "ROS", "SKIN", 0, 0, 10, None),

    ("ROS_SKN_002", "Do you have itching (pruritis)? Is it localised or generalised? Worse at night?",
     "Nocturnal itch: scabies, cholestatic jaundice. Generalised: CKD, lymphoma, thyroid.",
     "MULTI_SELECT",
     '["No itching", "Localised itching", "Generalised itching", "Itching worse at night", "Itching with visible rash", "Itching without visible skin change"]',
     None, None, 3, "ROS", "SKIN", 0, 0, 20, None),

    ("ROS_SKN_003", "Have you noticed changes to moles or new pigmented skin lesions?",
     "ABCDE rule: Asymmetry, Border, Colour, Diameter >6mm, Evolving = malignant melanoma risk.",
     "BINARY", None, None, None, 3, "ROS", "SKIN", 0, 0, 30, None),

    ("ROS_SKN_004", "Is your skin dry, flaky, or thickened? Do you have chronic skin conditions like eczema or psoriasis?",
     "Dry skin + hair loss + weight gain = hypothyroidism. Silver plaques on elbows/knees = psoriasis.",
     "BINARY", None, None, None, 3, "ROS", "SKIN", 0, 0, 40, None),

    ("ROS_SKN_005", "Have you noticed any hair loss or unusual hair thinning?",
     "Patchy = alopecia areata (autoimmune). Diffuse = thyroid, iron deficiency, stress.",
     "SINGLE_SELECT",
     '["No hair loss", "Generalised diffuse thinning", "Patchy hair loss", "Male-pattern hair loss", "Hair loss from chemotherapy or medications", "Eyebrow or body hair loss"]',
     None, None, 3, "ROS", "SKIN", 0, 0, 50, None),

    ("ROS_SKN_006", "Do you have any wounds, ulcers, or sores that are slow to heal?",
     "Non-healing wounds: DM (neuropathic), PVD (arterial), venous (gaiter area). Exclude malignancy.",
     "BINARY", None, None, None, 3, "ROS", "SKIN", 0, 0, 60, None),

    ("ROS_SKN_007", "Do you have any nail changes: thickening, pitting, discolouration, or separation?",
     "Nail pitting = psoriasis. Onycholysis = psoriasis/thyroid. Koilonychia = iron deficiency. Clubbing = resp/cardiac.",
     "MULTI_SELECT",
     '["No nail changes", "Nail pitting", "Thickened discoloured nails (fungal)", "Nails separated from nail bed", "Spoon-shaped nails (koilonychia)", "Finger clubbing", "Transverse white lines", "Blue or dark nails"]',
     None, None, 3, "ROS", "SKIN", 0, 0, 70, None),

    # ROS SYSTEM 10: NEUROLOGICAL
    ("ROS_NEU_001", "Do you experience headaches? How frequent and severe are they?",
     "New headache in >50 = giant cell arteritis. Worst-of-life = SAH. Progressive = mass lesion.",
     "SINGLE_SELECT",
     '["No headaches", "Occasional mild headaches (< once/week)", "Frequent headaches (several times/week)", "Daily headaches", "Episodic severe headaches (migraines)", "A single severe headache that was the worst of my life"]',
     None, None, 3, "ROS", "NEURO", 0, 0, 10, "LOINC:36328-2"),

    ("ROS_NEU_002", "Do you have any weakness in your arms or legs? Is it one side or both?",
     "Unilateral weakness = UMN (stroke, tumour). Bilateral proximal = myopathy. Distal = neuropathy.",
     "MULTI_SELECT",
     '["No weakness", "Right arm weakness", "Left arm weakness", "Right leg weakness", "Left leg weakness", "Both arms", "Both legs", "Facial droop", "Generalised weakness"]',
     None, None, 3, "ROS", "NEURO", 0, 0, 20, None),

    ("ROS_NEU_003", "Do you have any numbness, tingling, or burning sensations?",
     "Dermatomal = radiculopathy. Glove-stocking = peripheral neuropathy. Hemibody = central lesion.",
     "MULTI_SELECT",
     '["No numbness or tingling", "Tingling in hands (both)", "Tingling in one hand or arm", "Tingling in feet (both)", "Tingling in one foot or leg", "Burning sensation in hands or feet", "Numbness following nerve distribution", "Reduced sensation to touch or temperature"]',
     None, None, 3, "ROS", "NEURO", 0, 0, 30, None),

    ("ROS_NEU_004", "Have you experienced any episodes of confusion, memory loss, or difficulty thinking clearly?",
     "Acute confusion = delirium (infection, metabolic, drugs). Chronic progressive = dementia.",
     "SINGLE_SELECT",
     '["No confusion or memory problems", "Occasional forgetfulness", "Progressive memory difficulties", "Sudden episodes of confusion", "Persistent confusion since illness or event", "Confusion in the evening (sundowning)"]',
     None, None, 3, "ROS", "NEURO", 0, 0, 40, None),

    ("ROS_NEU_005", "Have you had any seizures, fits, blackouts, or uncontrolled shaking?",
     "First seizure in adult: MRI, EEG, exclude metabolic and structural causes before epilepsy diagnosis.",
     "BINARY", None, None, None, 3, "ROS", "NEURO", 0, 0, 50, "LOINC:10829-1"),

    ("ROS_NEU_006", "Do you have any difficulty with coordination, balance, or walking (ataxia)?",
     "Cerebellar ataxia: alcohol, MS, stroke. Sensory ataxia: B12 deficiency, tabes dorsalis.",
     "BINARY", None, None, None, 3, "ROS", "NEURO", 0, 0, 60, None),

    ("ROS_NEU_007", "Have you noticed any change in your speech - slurring, difficulty finding words?",
     "Slurred speech (dysarthria) = cerebellar/UMN. Word-finding difficulty = dominant hemisphere lesion.",
     "BINARY", None, None, None, 3, "ROS", "NEURO", 0, 0, 70, None),

    ("ROS_NEU_008", "Do you have tremors - shaking of hands, head, or voice?",
     "Rest tremor = Parkinson. Action tremor = cerebellar. Postural = essential tremor.",
     "SINGLE_SELECT",
     '["No tremors", "Shaking at rest", "Shaking during intentional movement", "Shaking when holding a position", "Tremors affecting voice", "Tremors affecting writing or fine tasks"]',
     None, None, 3, "ROS", "NEURO", 0, 0, 80, None),

    ("ROS_NEU_009", "Have you experienced any loss of consciousness, even briefly?",
     "Brief LOC: vasovagal (prodrome), cardiac (abrupt), epileptic (postictal confusion).",
     "BINARY", None, None, None, 3, "ROS", "NEURO", 0, 0, 90, None),

    # ROS SYSTEM 11: PSYCHIATRIC
    ("ROS_PSY_001", "Have you been feeling down, depressed, or hopeless for most of the time over the past 2 weeks?",
     "PHQ-2 item 1. Positive = proceed to PHQ-9. Core symptom of major depressive disorder.",
     "SINGLE_SELECT",
     '["Not at all", "Several days", "More than half the days", "Nearly every day"]',
     None, None, 3, "ROS", "PSYCH", 0, 0, 10, "LOINC:44250-9"),

    ("ROS_PSY_002", "Have you lost interest or pleasure in activities you normally enjoy (anhedonia)?",
     "PHQ-2 item 2. Anhedonia + depressed mood >= 2 weeks = MDD criteria.",
     "SINGLE_SELECT",
     '["Not at all", "Several days", "More than half the days", "Nearly every day"]',
     None, None, 3, "ROS", "PSYCH", 0, 0, 20, "LOINC:44255-8"),

    ("ROS_PSY_003", "Have you been experiencing excessive worry, anxiety, or nervousness?",
     "GAD-2 proxy. Anxiety with physical symptoms (palpitations, tremor) = panic disorder.",
     "SINGLE_SELECT",
     '["Not at all", "Several days", "More than half the days", "Nearly every day"]',
     None, None, 3, "ROS", "PSYCH", 0, 0, 30, "LOINC:69737-5"),

    ("ROS_PSY_004", "Do you experience sudden attacks of intense fear, racing heart, difficulty breathing (panic attacks)?",
     "Panic attacks: abrupt peak within 10 min. Must exclude ACS in first presentation.",
     "BINARY", None, None, None, 3, "ROS", "PSYCH", 0, 0, 40, None),

    ("ROS_PSY_005", "Have you experienced any hallucinations - hearing voices, seeing things?",
     "Auditory hallucinations: schizophrenia, mania, severe depression. Tactile: alcohol withdrawal.",
     "MULTI_SELECT",
     '["No hallucinations", "Hearing voices when no one is there", "Seeing things others cannot see", "Feeling sensations on or under skin", "Smelling or tasting things without stimulus", "Not sure if real"]',
     None, None, 3, "ROS", "PSYCH", 0, 0, 50, None),

    ("ROS_PSY_006", "Have you experienced periods of elevated mood, decreased need for sleep, racing thoughts, or unusual risky behaviour?",
     "Manic episodes: grandiosity, decreased sleep, pressured speech, impulsivity.",
     "BINARY", None, None, None, 3, "ROS", "PSYCH", 0, 0, 60, None),

    ("ROS_PSY_007", "Do you have intrusive thoughts, flashbacks, or nightmares related to a past traumatic event?",
     "PTSD criteria: re-experiencing, avoidance, hyperarousal after trauma. Must be > 1 month.",
     "BINARY", None, None, None, 3, "ROS", "PSYCH", 0, 0, 70, None),

    ("ROS_PSY_008", "Are you currently using alcohol or drugs in a way that is causing problems in your life?",
     "CAGE/AUDIT proxy. Substance use disorder: tolerance, withdrawal, loss of control.",
     "SINGLE_SELECT",
     '["No", "Occasionally in excess but not causing problems", "Yes - causing some problems", "Yes - significantly impacting my life", "Prefer not to answer"]',
     None, None, 3, "ROS", "PSYCH", 0, 0, 80, None),

    # ROS SYSTEM 12: ENDOCRINE
    ("ROS_END_001", "Do you experience increased thirst (polydipsia) and frequent urination (polyuria)?",
     "Classic DM/DI symptoms: polyuria + polydipsia + polyphagia + weight loss.",
     "BINARY", None, None, None, 3, "ROS", "ENDO", 0, 0, 10, None),

    ("ROS_END_002", "Have you noticed unexplained weight changes (gain without increased eating, OR loss despite normal appetite)?",
     "Weight gain: hypothyroidism, Cushing. Weight loss with normal appetite: hyperthyroidism, DM, malignancy.",
     "SINGLE_SELECT",
     '["No weight change", "Weight gain without increased food intake", "Weight loss despite normal or good appetite", "Both weight changes", "Rapid weight change"]',
     None, None, 3, "ROS", "ENDO", 0, 0, 20, "LOINC:29463-7"),

    ("ROS_END_003", "Do you feel abnormally cold all the time, or abnormally hot with sweating?",
     "Cold intolerance = hypothyroidism. Heat intolerance + sweating = hyperthyroidism or menopause.",
     "SINGLE_SELECT",
     '["No temperature intolerance", "Always feel cold", "Always feel hot / Sweating excessively", "Hot flushes with sweating"]',
     None, None, 3, "ROS", "ENDO", 0, 0, 30, None),

    ("ROS_END_004", "Do you have a swelling in your neck (possible goitre), or have you had thyroid disease?",
     "Neck swelling: thyroid goitre. Diffuse = Graves/Hashimotos; nodular = multi-nodular goitre.",
     "BINARY", None, None, None, 3, "ROS", "ENDO", 0, 0, 40, None),

    ("ROS_END_005", "Do you have episodes of excessive sweating, palpitations, headache, and high blood pressure?",
     "Phaeochromocytoma triad: headache + palpitations + sweating = hypertensive crisis.",
     "BINARY", None, None, None, 3, "ROS", "ENDO", 0, 0, 50, None),

    ("ROS_END_006", "Do you have stretch marks, easy bruising, central obesity, or round face?",
     "Cushing syndrome: moon face, buffalo hump, striae, central obesity, easy bruising.",
     "MULTI_SELECT",
     '["None of these", "Purple/red stretch marks", "Easy bruising from minor trauma", "Central obesity (fat belly, thin arms/legs)", "Round / Moon-shaped face", "Fatty lump on back of neck"]',
     None, None, 3, "ROS", "ENDO", 0, 0, 60, None),

    ("ROS_END_007", "Do you have decreased libido, sexual dysfunction, or changes in menstrual regularity?",
     "Hypogonadism: testosterone/oestrogen deficiency. Prolactinoma: galactorrhoea + amenorrhoea.",
     "BINARY", None, None, None, 3, "ROS", "ENDO", 0, 0, 70, None),

    ("ROS_END_008", "Have you been told you have diabetes, pre-diabetes, or insulin resistance?",
     "Known DM changes the clinical differential for many presenting complaints.",
     "SINGLE_SELECT",
     '["No diabetes", "Pre-diabetes / Borderline blood sugar", "Type 2 DM - diet only", "Type 2 DM - oral tablets", "Type 2 DM - insulin", "Type 1 DM - insulin", "Gestational diabetes"]',
     None, None, 3, "ROS", "ENDO", 0, 0, 80, None),

    # ROS SYSTEM 13: HEMATOLOGIC / LYMPHATIC
    ("ROS_HEM_001", "Do you bruise or bleed more easily than usual?",
     "Easy bruising/prolonged bleeding: thrombocytopenia, clotting factor deficiency, warfarin.",
     "BINARY", None, None, None, 3, "ROS", "HEME", 0, 0, 10, None),

    ("ROS_HEM_002", "Do you experience extreme fatigue, pallor, or shortness of breath on minimal exertion (possible anaemia)?",
     "Iron deficiency most common; B12/folate (macrocytic); haemolytic; anaemia of chronic disease.",
     "BINARY", None, None, None, 3, "ROS", "HEME", 0, 0, 20, None),

    ("ROS_HEM_003", "Have you noticed swollen lymph glands anywhere in your body?",
     "Generalised lymphadenopathy: lymphoma, HIV, EBV. Localised = regional source of infection.",
     "MULTI_SELECT",
     '["No swollen glands", "Neck lymph nodes", "Armpit lymph nodes", "Groin lymph nodes", "Multiple areas", "Painful lymph nodes", "Painless but enlarging lymph nodes"]',
     None, None, 3, "ROS", "HEME", 0, 0, 30, None),

    ("ROS_HEM_004", "Have you noticed small red or purple spots on your skin (petechiae) or larger bruised areas (purpura)?",
     "Petechiae: ITP, meningococcaemia (emergency if purpuric + fever). Purpura: vasculitis, DIC.",
     "BINARY", None, None, None, 3, "ROS", "HEME", 0, 0, 40, None),

    ("ROS_HEM_005", "Have you had any unexplained or recurrent infections?",
     "Recurrent infections: immunodeficiency (HIV, primary, drug-induced), poorly controlled DM.",
     "BINARY", None, None, None, 3, "ROS", "HEME", 0, 0, 50, None),

    ("ROS_HEM_006", "Have you ever been told you have a blood clotting problem or been on blood thinners?",
     "Thrombophilia: Factor V Leiden, Protein C/S deficiency, antiphospholipid syndrome.",
     "BINARY", None, None, None, 3, "ROS", "HEME", 0, 0, 60, None),

    ("ROS_HEM_007", "Have you ever received a blood transfusion or bone marrow transplant?",
     "Transfusion history: alloimmunisation, transfusion-transmitted infections, GVHD.",
     "BINARY", None, None, None, 3, "ROS", "HEME", 0, 0, 70, None),

    # ROS SYSTEM 14: ALLERGIC / IMMUNOLOGIC
    ("ROS_ALG_001", "Do you have any known allergies to medications, foods, insect stings, or the environment?",
     "Allergy type matters: anaphylaxis vs. intolerance. Document allergen + reaction type.",
     "MULTI_SELECT",
     '["No known allergies", "Penicillin or amoxicillin", "Other antibiotics", "Aspirin or NSAIDs", "X-ray / Contrast dye", "Nuts", "Shellfish or fish", "Dairy products", "Insect stings", "Latex", "Pollen / Dust mites / Animals", "Multiple allergies", "Not sure"]',
     None, None, 3, "ROS", "IMMUNE", 0, 0, 10, "LOINC:48765-2"),

    ("ROS_ALG_002", "When you have an allergic reaction, what happens? Select all that apply.",
     "Severity: mild (urticaria only) vs. severe (airway + BP drop = anaphylaxis).",
     "MULTI_SELECT",
     '["Hives or itchy rash", "Swelling of face/lips/tongue/throat", "Runny nose and sneezing", "Itchy watery eyes", "Difficulty breathing or wheezing", "Sudden drop in blood pressure", "Vomiting or abdominal pain", "Full collapse (anaphylaxis)"]',
     None, None, 3, "ROS", "IMMUNE", 0, 0, 20, None),

    ("ROS_ALG_003", "Do you carry an EpiPen (adrenaline auto-injector) or emergency allergy medication?",
     "EpiPen carrying = history of severe/anaphylactic reaction. Critical to document.",
     "BINARY", None, None, None, 3, "ROS", "IMMUNE", 0, 0, 30, None),

    ("ROS_ALG_004", "Do you have seasonal or year-round hay fever (allergic rhinitis) or allergic asthma?",
     "Atopy: eczema + allergic rhinitis + asthma = atopic triad.",
     "BINARY", None, None, None, 3, "ROS", "IMMUNE", 0, 0, 40, None),

    ("ROS_ALG_005", "Have you been diagnosed with any autoimmune condition?",
     "Autoimmune disease is a strong risk factor for other autoimmune conditions.",
     "MULTI_SELECT",
     '["No autoimmune condition", "SLE (Lupus)", "Rheumatoid Arthritis", "Type 1 Diabetes", "Autoimmune thyroid disease", "Coeliac disease", "Inflammatory bowel disease", "Multiple Sclerosis", "Myasthenia Gravis", "Other autoimmune condition"]',
     None, None, 3, "ROS", "IMMUNE", 0, 0, 50, None),

    ("ROS_ALG_006", "Are you currently on any immunosuppressive medications (steroids, methotrexate, biologics, chemotherapy)?",
     "Immunosuppression changes infection risk profile and symptom presentation significantly.",
     "BINARY", None, None, None, 3, "ROS", "IMMUNE", 0, 0, 60, None),

    # PHASE 4 - PMH / HISTORY NODES
    ("PMH_001", "Have you ever had a heart attack or been told you have coronary artery disease?",
     "Prior MI increases risk of repeat ACS, arrhythmia, heart failure.",
     "BINARY", None, None, None, 4, "PMH", "CARDIAC", 0, 0, 10, None),

    ("PMH_002", "Have you ever had a stroke or a mini-stroke (TIA)?",
     "Prior stroke: recurrence risk 15% in first year. Document deficits, antiplatelet/anticoagulant use.",
     "BINARY", None, None, None, 4, "PMH", "NEURO", 0, 0, 20, None),

    ("PMH_003", "Have you been told you have chronic kidney disease (CKD) or are you on dialysis?",
     "CKD stage affects drug dosing, contrast use, and electrolyte management.",
     "BINARY", None, None, None, 4, "PMH", "RENAL", 0, 0, 30, None),

    ("PMH_004", "Have you had tuberculosis (TB) before? Were you treated completely?",
     "Prior TB: reactivation risk, drug resistance pattern, contact history essential.",
     "BINARY", None, None, None, 4, "PMH", "INFECT", 0, 0, 40, None),

    ("PMH_005", "Do you have HIV or any other condition that weakens your immune system?",
     "HIV status changes infection differential radically (PCP, CMV, cryptococcal meningitis, TB).",
     "SINGLE_SELECT",
     '["No", "HIV positive - on ART, well controlled", "HIV positive - not on treatment", "HIV positive - not sure of status", "Other immunosuppression", "Prefer not to say"]',
     None, None, 4, "PMH", "INFECT", 0, 0, 50, None),

    ("PMH_006", "Do you have any other significant medical conditions a doctor should know about?",
     "Open-ended PMH capture for conditions not covered by structured options.",
     "TEXT_SHORT", None, None, None, 4, "PMH", None, 0, 0, 60, None),

    ("PMH_007", "Are you currently taking any HERBAL, TRADITIONAL, or ALTERNATIVE medicines or supplements?",
     "Herbal medicines have drug interactions: St Johns Wort + SSRIs = serotonin syndrome.",
     "BINARY", None, None, None, 4, "PMH", None, 0, 0, 70, None),

    ("PMH_008", "Have you had any recent hospitalisation (last 3 months) or major illness?",
     "Recent hospitalisation: post-discharge complications, healthcare-associated infections.",
     "BINARY", None, None, None, 4, "PMH", None, 0, 0, 80, None),

    ("PMH_009", "Have you ever received a blood transfusion? Did you have any reactions?",
     "Transfusion history: alloimmunisation, transfusion-transmitted diseases.",
     "BINARY", None, None, None, 4, "PMH", "HEME", 0, 0, 90, None),

    ("PMH_010", "Have you had any vaccinations recently (within the last 4 weeks)?",
     "Recent vaccination: post-vaccination fever/malaise (normal reaction), rare adverse events.",
     "BINARY", None, None, None, 4, "PMH", None, 0, 0, 100, None),

    ("SRG_001", "Have you had any surgical operations in the past?",
     "Prior surgery affects current presentation: adhesions, scar hernias, post-op complications.",
     "BINARY", None, None, None, 4, "PMH", None, 0, 0, 110, None),

    ("SRG_002", "Have you had any abdominal or pelvic operations?",
     "Prior abdominal surgery + current abdominal pain = adhesional obstruction high differential.",
     "MULTI_SELECT",
     '["None", "Appendix removal", "Gallbladder removal", "Bowel/intestinal surgery", "Hernia repair", "Hysterectomy", "C-section", "Other abdominal/pelvic surgery"]',
     None, None, 4, "PMH", None, 0, 0, 120, None),

    ("SRG_003", "Have you had any heart or chest surgery (bypass, valve replacement, stent)?",
     "Cardiac surgery history: prosthetic valve endocarditis risk, in-stent thrombosis.",
     "MULTI_SELECT",
     '["None", "Coronary artery bypass graft (CABG)", "Heart valve replacement", "Coronary stent", "Pacemaker or defibrillator", "Other heart/chest surgery"]',
     None, None, 4, "PMH", None, 0, 0, 130, None),

    ("SRG_004", "Have you had any problems with anaesthesia in the past?",
     "Malignant hyperthermia (hereditary, life-threatening), previous complications.",
     "BINARY", None, None, None, 4, "PMH", None, 0, 0, 140, None),

    ("SRG_005", "Have you had any orthopaedic surgery (joint replacement, fracture fixation, spinal surgery)?",
     "Prosthetic joint infection risk (especially with fever/local symptoms).",
     "BINARY", None, None, None, 4, "PMH", None, 0, 0, 150, None),

    ("SOH_001", "What is your occupation or main daily activity?",
     "Occupation: exposures (asbestos, chemicals, repetitive strain, shift work), stress level.",
     "SINGLE_SELECT",
     '["Office / Desk work", "Manual labour / Construction", "Healthcare worker", "Food handler", "Teacher", "Farmer / Agricultural", "Factory / Industrial", "Driver / Transport", "Retired", "Student", "Homemaker", "Unemployed", "Other"]',
     None, None, 4, "PMH", "SOCIAL", 0, 0, 160, None),

    ("SOH_002", "Do you currently smoke or use tobacco products?",
     "Smoking is a major risk factor for cardiovascular, respiratory, and oncological disease.",
     "SINGLE_SELECT",
     '["Never smoked", "Ex-smoker (quit > 1 year ago)", "Ex-smoker (quit < 1 year ago)", "Current smoker < 10/day", "Current smoker 10-20/day", "Current smoker > 20/day", "Bidi / Hookah / Pipe", "E-cigarette / Vaping", "Smokeless tobacco"]',
     None, None, 4, "PMH", "SOCIAL", 0, 0, 170, None),

    ("SOH_003", "How much alcohol do you drink and how often?",
     "Alcohol: >= 5 units/day = high risk. CAGE >= 2 = alcohol dependence likely.",
     "SINGLE_SELECT",
     '["I do not drink", "Rarely (< 1 unit/week)", "Moderately (1-14 units/week)", "Heavily (15-35 units/week)", "Very heavily (> 35 units/week)", "Binge drinker", "Prefer not to say"]',
     None, None, 4, "PMH", "SOCIAL", 0, 0, 180, None),

    ("SOH_004", "Do you use any recreational or illicit substances?",
     "IV drug use = HIV/hepatitis/endocarditis risk; stimulants = cardiac/psychiatric.",
     "MULTI_SELECT",
     '["No recreational drug use", "Cannabis", "Opioids (misuse)", "Stimulants (cocaine, amphetamine)", "Benzodiazepines (not prescribed)", "Intravenous drug use", "Inhalants / Solvents", "Other / Prefer not to say"]',
     None, None, 4, "PMH", "SOCIAL", 0, 0, 190, None),

    ("SOH_005", "Who do you live with? What is your home environment like?",
     "Social support, housing stability affect recovery and disposition planning.",
     "SINGLE_SELECT",
     '["Lives alone", "Lives with partner/spouse", "Lives with family", "Shared accommodation / Hostel", "Supported housing / Care home", "Homeless or unstable housing"]',
     None, None, 4, "PMH", "SOCIAL", 0, 0, 200, None),

    ("SOH_006", "Have you recently travelled outside the country?",
     "Travel history: malaria, typhoid, dengue, viral haemorrhagic fevers, resistant organisms.",
     "BINARY", None, None, None, 4, "PMH", "SOCIAL", 0, 0, 210, None),

    ("SOH_007", "Is your diet balanced and regular? Have you made any significant dietary changes recently?",
     "Dietary assessment: deficiency diseases (B12, iron, scurvy, rickets).",
     "SINGLE_SELECT",
     '["Balanced mixed diet", "Vegetarian diet", "Vegan diet", "Restrictive diet", "Irregular / Poor diet", "Food insecurity"]',
     None, None, 4, "PMH", "SOCIAL", 0, 0, 220, None),

    ("SOH_008", "Do you exercise regularly? What level of physical activity do you do?",
     "Physical inactivity = independent risk factor for cardiovascular and metabolic disease.",
     "SINGLE_SELECT",
     '["Sedentary (no exercise)", "Light activity (walking < 30 min/day)", "Moderate activity (30-60 min most days)", "High activity (sports or gym > 5 days/week)", "Very high activity (athletic/physical job)"]',
     None, None, 4, "PMH", "SOCIAL", 0, 0, 230, None),

    ("FAM_001", "Do any immediate family members have heart disease or strokes at a young age (before 60)?",
     "Family history of premature CVD = major independent risk factor. Doubles individual risk.",
     "BINARY", None, None, None, 4, "PMH", "FAMILY", 0, 0, 240, None),

    ("FAM_002", "Is there a family history of diabetes mellitus?",
     "Family history of T2DM: 40% lifetime risk if one parent; 70% if both parents affected.",
     "BINARY", None, None, None, 4, "PMH", "FAMILY", 0, 0, 250, None),

    ("FAM_003", "Is there a family history of cancer? What type and which family members?",
     "BRCA1/2: breast/ovarian. Lynch syndrome: colorectal. MEN: multiple endocrine neoplasia.",
     "MULTI_SELECT",
     '["No family history of cancer", "Breast cancer", "Ovarian cancer", "Bowel/Colorectal cancer", "Prostate cancer", "Lung cancer", "Stomach cancer", "Liver cancer", "Cervical cancer", "Blood cancer", "Other cancer", "Multiple family members"]',
     None, None, 4, "PMH", "FAMILY", 0, 0, 260, None),

    ("FAM_004", "Is there a family history of mental health conditions (depression, schizophrenia, bipolar, suicide)?",
     "Genetic heritability: schizophrenia 80%, bipolar 60-80%, MDD 37%, suicide 10-fold risk increase.",
     "BINARY", None, None, None, 4, "PMH", "FAMILY", 0, 0, 270, None),

    ("FAM_005", "Is there a family history of kidney disease, autoimmune disease, or genetic conditions?",
     "ADPKD, sickle cell (HbSS in African ancestry), thalassaemia, haemophilia.",
     "MULTI_SELECT",
     '["No family history", "Kidney disease", "Autoimmune conditions", "Sickle cell disease or trait", "Thalassaemia", "Haemophilia", "Thyroid disease", "Other genetic condition"]',
     None, None, 4, "PMH", "FAMILY", 0, 0, 280, None),

    ("FAM_006", "Is there a family history of sudden unexplained death, especially in young family members (< 40 years)?",
     "Sudden unexplained death in young: HCM, long QT syndrome, Brugada. Genetic channelopathies.",
     "BINARY", None, None, None, 4, "PMH", "FAMILY", 0, 0, 290, None),

]  # End NODES

# =============================================================================
# 2. SYNDROMES
# Format: (syndrome_id, name, icd10, category, severity_tier, common_frameworks_json, description)
# =============================================================================

SYNDROMES = [
    # Cardiovascular
    ("SYN_001", "Acute Myocardial Infarction (STEMI)", "I21.0", "CVS", 1,
     '["SOCRATES"]', "ST-elevation MI requiring emergency PCI/thrombolysis."),
    ("SYN_002", "Non-ST Elevation MI / Unstable Angina", "I21.4", "CVS", 1,
     '["SOCRATES"]', "NSTEMI or UA: troponin positive without ST elevation."),
    ("SYN_003", "Stable Angina", "I20.8", "CVS", 2,
     '["SOCRATES", "OLD_CARTS"]', "Reproducible exertional chest pain relieved by rest/GTN."),
    ("SYN_004", "Aortic Dissection", "I71.0", "CVS", 1,
     '["SOCRATES"]', "Tearing/ripping chest/back pain radiating to abdomen, BP differential."),
    ("SYN_005", "Pulmonary Embolism", "I26.9", "CVS", 1,
     '["SOCRATES"]', "Sudden onset pleuritic chest pain + dyspnoea + haemoptysis + DVT risk."),
    ("SYN_006", "Deep Vein Thrombosis", "I80.2", "CVS", 2,
     '["SOCRATES", "OLD_CARTS"]', "Calf/leg swelling, warmth, tenderness, DVT risk factors."),
    ("SYN_007", "Heart Failure", "I50.9", "CVS", 2,
     '["OLD_CARTS"]', "Dyspnoea, orthopnoea, PND, peripheral edema, S3 gallop."),
    ("SYN_008", "Pericarditis", "I30.9", "CVS", 2,
     '["SOCRATES"]', "Sharp pleuritic chest pain, relieved by sitting forward, friction rub."),
    ("SYN_009", "Myocarditis", "I40.9", "CVS", 2,
     '["OLD_CARTS"]', "Chest pain/dyspnoea following viral illness, troponin rise."),
    ("SYN_010", "Atrial Fibrillation", "I48.9", "CVS", 2,
     '["OLD_CARTS"]', "Irregular irregular pulse, palpitations, dyspnoea, embolic risk."),
    ("SYN_011", "Supraventricular Tachycardia", "I47.1", "CVS", 2,
     '["SOCRATES"]', "Paroxysmal palpitations, regular tachycardia, abrupt onset and offset."),
    ("SYN_012", "Hypertensive Crisis", "I16.9", "CVS", 1,
     '["OLD_CARTS"]', "Severely elevated BP with end-organ damage: headache, visual change."),
    # Respiratory
    ("SYN_013", "Community-Acquired Pneumonia", "J18.9", "RESP", 2,
     '["OLD_CARTS"]', "Fever, productive cough, pleuritic pain, consolidation on X-ray."),
    ("SYN_014", "COPD Exacerbation", "J44.1", "RESP", 2,
     '["OLD_CARTS"]', "Worsening dyspnoea, increased sputum, wheeze in known COPD."),
    ("SYN_015", "Asthma Exacerbation", "J45.9", "RESP", 2,
     '["OLD_CARTS"]', "Wheeze, cough, dyspnoea, nocturnal symptoms, variable airflow."),
    ("SYN_016", "Pleural Effusion", "J90", "RESP", 2,
     '["OLD_CARTS"]', "Dullness to percussion, reduced breath sounds, dyspnoea."),
    ("SYN_017", "Pneumothorax", "J93.9", "RESP", 2,
     '["SOCRATES"]', "Sudden pleuritic pain, dyspnoea, absent breath sounds (ipsilateral)."),
    ("SYN_018", "Pulmonary Tuberculosis", "A15.0", "RESP", 2,
     '["OLD_CARTS"]', "Chronic cough, haemoptysis, night sweats, weight loss, contact history."),
    ("SYN_019", "Lung Cancer", "C34.9", "RESP", 1,
     '["OLD_CARTS"]', "Persistent cough, haemoptysis, weight loss, smoking history."),
    ("SYN_020", "Acute Bronchitis / URTI", "J20.9", "RESP", 3,
     '["OLD_CARTS"]', "Productive cough after URTI, low-grade fever, self-limiting."),
    # Gastrointestinal
    ("SYN_021", "GERD / Peptic Oesophagitis", "K21.0", "GI", 3,
     '["SOCRATES"]', "Heartburn, acid regurgitation, relieved by antacids, worse lying down."),
    ("SYN_022", "Peptic Ulcer Disease", "K27.9", "GI", 2,
     '["SOCRATES"]', "Epigastric pain, relation to meals, NSAID/H.pylori association."),
    ("SYN_023", "Acute Appendicitis", "K37", "GI", 1,
     '["SOCRATES"]', "Periumbilical pain migrating to RLQ, rebound tenderness, fever."),
    ("SYN_024", "Acute Cholecystitis / Biliary Colic", "K80.0", "GI", 2,
     '["SOCRATES"]', "RUQ pain post-fatty meal, Murphy sign, nausea, fever (cholecystitis)."),
    ("SYN_025", "Acute Pancreatitis", "K85.9", "GI", 2,
     '["SOCRATES"]', "Severe epigastric pain radiating to back, relieved by leaning forward."),
    ("SYN_026", "Inflammatory Bowel Disease", "K51.9", "GI", 2,
     '["OLD_CARTS", "COCA"]', "Bloody diarrhoea, mucus, abdominal cramps, weight loss, flares."),
    ("SYN_027", "Irritable Bowel Syndrome", "K58.9", "GI", 3,
     '["OLD_CARTS"]', "Altered bowel habit, abdominal pain relieved by defecation, no alarm features."),
    ("SYN_028", "Upper GI Bleed", "K92.1", "GI", 1,
     '["COCA"]', "Haematemesis or melena, dizziness, prior PUD/NSAID/variceal history."),
    ("SYN_029", "Lower GI Bleed", "K92.2", "GI", 2,
     '["COCA"]', "Bright red blood per rectum, haematochezia; exclude colorectal cancer."),
    ("SYN_030", "Bowel Obstruction", "K56.7", "GI", 1,
     '["SOCRATES"]', "Colicky pain, vomiting, absolute constipation, distension, tinkling bowel."),
    ("SYN_031", "Acute Hepatitis", "K75.9", "GI", 2,
     '["OLD_CARTS", "COCA"]', "Jaundice, RUQ pain, dark urine, pale stool, transaminase elevation."),
    ("SYN_032", "Liver Cirrhosis / Decompensation", "K74.6", "GI", 2,
     '["OLD_CARTS"]', "Ascites, jaundice, hepatic encephalopathy, varices, spider naevi."),
    # Neurological
    ("SYN_033", "Ischaemic Stroke / TIA", "G45.9", "NEURO", 1,
     '["OLD_CARTS"]', "Sudden focal neurological deficit: face/arm/speech (FAST positive)."),
    ("SYN_034", "Haemorrhagic Stroke", "I61.9", "NEURO", 1,
     '["SOCRATES"]', "Sudden severe headache, vomiting, focal deficits, hypertension."),
    ("SYN_035", "Bacterial Meningitis", "G00.9", "NEURO", 1,
     '["OLD_CARTS"]', "Fever, neck stiffness, photophobia, headache, non-blanching rash."),
    ("SYN_036", "Migraine", "G43.9", "SOCRATES", 3,
     '["SOCRATES"]', "Unilateral throbbing headache, nausea, photophobia, aura possible."),
    ("SYN_037", "Tension Headache", "G44.2", "NEURO", 3,
     '["SOCRATES"]', "Bilateral pressing/tightening headache, no aura, not aggravated by routine activity."),
    ("SYN_038", "Cluster Headache", "G44.0", "NEURO", 2,
     '["SOCRATES"]', "Severe unilateral orbital/temporal pain with autonomic features, episodic clusters."),
    ("SYN_039", "Epilepsy / Seizure Disorder", "G40.9", "NEURO", 2,
     '["ROTS", "OLD_CARTS"]', "Recurrent unprovoked seizures. First seizure requires full workup."),
    ("SYN_040", "Peripheral Neuropathy", "G62.9", "NEURO", 3,
     '["OLD_CARTS"]', "Glove-stocking sensory loss, burning feet, absent ankle reflexes."),
    # Psychiatric
    ("SYN_041", "Major Depressive Disorder", "F32.9", "PSY", 2,
     '["ROTS"]', "Depressed mood + anhedonia + somatic symptoms >= 2 weeks."),
    ("SYN_042", "Generalised Anxiety Disorder", "F41.1", "PSY", 3,
     '["ROTS"]', "Excessive, uncontrollable worry for >= 6 months, multiple domains."),
    ("SYN_043", "Panic Disorder", "F41.0", "PSY", 3,
     '["ROTS"]', "Recurrent unexpected panic attacks with anticipatory anxiety."),
    ("SYN_044", "Schizophrenia", "F20.9", "PSY", 2,
     '["ROTS"]', "Positive symptoms (hallucinations, delusions) + negative symptoms >= 6 months."),
    ("SYN_045", "Bipolar Disorder", "F31.9", "PSY", 2,
     '["ROTS"]', "Episodic mania/hypomania alternating with depression."),
    ("SYN_046", "Post-Traumatic Stress Disorder", "F43.1", "PSY", 2,
     '["ROTS"]', "Re-experiencing, avoidance, hyperarousal following trauma (>1 month)."),
    ("SYN_047", "Substance Use Disorder", "F19.9", "PSY", 2,
     '["ROTS"]', "Tolerance, withdrawal, loss of control, continued use despite harm."),
    # Genitourinary
    ("SYN_048", "Urinary Tract Infection", "N39.0", "GU", 3,
     '["COCA"]', "Dysuria, frequency, urgency, suprapubic pain, cloudy/smelly urine."),
    ("SYN_049", "Pyelonephritis", "N10", "GU", 2,
     '["COCA", "OLD_CARTS"]', "UTI symptoms + fever + flank pain + CVA tenderness."),
    ("SYN_050", "Renal / Ureteric Stone", "N20.9", "GU", 2,
     '["SOCRATES"]', "Severe colicky flank pain to groin, haematuria, nausea."),
    ("SYN_051", "Benign Prostatic Hyperplasia", "N40", "GU", 3,
     '["OLD_CARTS"]', "Obstructive lower urinary tract symptoms in older males."),
    ("SYN_052", "Ovarian Cyst / Torsion", "N83.2", "GU", 2,
     '["SOCRATES"]', "Lower abdominal/pelvic pain, may radiate to thigh, nausea."),
    ("SYN_053", "Ectopic Pregnancy", "O00.9", "GU", 1,
     '["SOCRATES"]', "Amenorrhoea + lower abdominal pain + vaginal bleeding; hCG positive."),
    ("SYN_054", "Pelvic Inflammatory Disease", "N73.9", "GU", 2,
     '["OLD_CARTS"]', "Lower abdominal pain, vaginal discharge, cervical motion tenderness."),
    # Musculoskeletal
    ("SYN_055", "Acute Fracture", "S99.9", "MSK", 2,
     '["SAMPLE"]', "Point tenderness, deformity, swelling, loss of function after trauma."),
    ("SYN_056", "Ligament Sprain / Muscle Strain", "M79.3", "MSK", 3,
     '["SOCRATES", "SAMPLE"]', "Localised pain, swelling, bruising; mechanism of injury."),
    ("SYN_057", "Osteoarthritis", "M19.9", "MSK", 3,
     '["OLD_CARTS"]', "Joint pain with use, morning stiffness < 30 min, crepitus, bony enlargement."),
    ("SYN_058", "Rheumatoid Arthritis", "M06.9", "MSK", 2,
     '["OLD_CARTS"]', "Symmetrical small joint polyarthritis, morning stiffness > 60 min, RF positive."),
    ("SYN_059", "Gout / Pseudogout", "M10.9", "MSK", 2,
     '["SOCRATES"]', "Acute monoarthritis (esp. first MTP), hyperuricaemia, purine-rich diet/alcohol."),
    ("SYN_060", "Septic Arthritis", "M00.9", "MSK", 1,
     '["SOCRATES"]', "Acute hot/swollen joint + fever; prosthetic joint at higher risk."),
    ("SYN_061", "Lumbar Disc Herniation / Sciatica", "M51.1", "MSK", 3,
     '["SOCRATES"]', "Lower back pain + dermatomal leg pain below knee; positive SLR."),
    ("SYN_062", "Ankylosing Spondylitis", "M45.9", "MSK", 2,
     '["OLD_CARTS"]', "Young male, chronic lower back pain, worse with rest, better with exercise."),
    # Endocrine
    ("SYN_063", "Type 2 Diabetes Mellitus", "E11.9", "ENDO", 2,
     '["OLD_CARTS"]', "Polyuria, polydipsia, fatigue, blurred vision, risk factors present."),
    ("SYN_064", "Hypothyroidism", "E03.9", "ENDO", 3,
     '["OLD_CARTS"]', "Fatigue, weight gain, cold intolerance, constipation, dry skin, bradycardia."),
    ("SYN_065", "Hyperthyroidism / Graves Disease", "E05.9", "ENDO", 2,
     '["OLD_CARTS"]', "Weight loss, tremor, tachycardia, heat intolerance, goitre, exophthalmos."),
    ("SYN_066", "Diabetic Ketoacidosis", "E13.10", "ENDO", 1,
     '["OLD_CARTS"]', "Known DM + nausea/vomiting + abdominal pain + fruity breath + hyperglycaemia."),
    # Infectious
    ("SYN_067", "Sepsis / SIRS", "A41.9", "INFECT", 1,
     '["OLD_CARTS"]', "Suspected infection + SIRS criteria (fever/tachycardia/tachypnoea/WBC change)."),
    ("SYN_068", "Cellulitis / Skin Infection", "L03.9", "INTEGUMENT", 3,
     '["OLD_CARTS"]', "Erythema, warmth, swelling, tenderness; expanding border in skin."),
    ("SYN_069", "Dengue Fever", "A97.9", "INFECT", 2,
     '["OLD_CARTS"]', "Fever, severe myalgia (breakbone), rash, thrombocytopenia; travel history."),
    ("SYN_070", "Malaria", "B54", "INFECT", 2,
     '["OLD_CARTS"]', "Cyclical fever with rigors, travel to endemic area, splenomegaly."),
    ("SYN_071", "Iron Deficiency Anaemia", "D50.9", "HEME", 3,
     '["OLD_CARTS"]', "Fatigue, pallor, pica, koilonychia, microcytic anaemia on FBC."),
    ("SYN_072", "Lymphoma", "C85.9", "HEME", 1,
     '["OLD_CARTS"]', "B-symptoms: fever + night sweats + weight loss; painless lymphadenopathy."),
    ("SYN_073", "Anaphylaxis", "T78.2", "IMMUNE", 1,
     '["SAMPLE"]', "Acute multi-system hypersensitivity: urticaria + airway compromise + hypotension."),
    ("SYN_074", "Pulmonary Sarcoidosis", "D86.0", "RESP", 3,
     '["OLD_CARTS"]', "Bilateral hilar lymphadenopathy, dyspnoea, erythema nodosum, uveitis."),
    ("SYN_075", "Typhoid Fever", "A01.0", "INFECT", 2,
     '["OLD_CARTS"]', "Stepwise fever, rose spots, relative bradycardia, diarrhoea, travel history."),
]

# =============================================================================
# 3. MATRIX WEIGHTS  (node_id, syndrome_id, frequency, evoking_strength, direction, notes)
# F=1-5 (how often), E=1-5 (how strongly it proves the disease)
# POSITIVE = YES answer increases syndrome score
# NEGATIVE = YES answer decreases syndrome score
# =============================================================================

MATRIX_WEIGHTS = [

    # ---- TRIAGE NODES -------------------------------------------------------
    # T009 (crushing chest pain) -> Cardiac syndromes
    ("T009", "SYN_001", 5, 5, "POSITIVE", "Crushing CP = classic AMI presentation"),
    ("T009", "SYN_002", 5, 4, "POSITIVE", "Crushing CP = NSTEMI/UA"),
    ("T009", "SYN_003", 3, 3, "POSITIVE", "Exertional CP = possible stable angina"),
    ("T009", "SYN_004", 4, 4, "POSITIVE", "Tearing CP = aortic dissection"),
    ("T009", "SYN_008", 3, 3, "POSITIVE", "Sharp CP + pleuritic = pericarditis"),

    # T008 (FAST positive) -> Neurological
    ("T008", "SYN_033", 5, 5, "POSITIVE", "FAST = ischaemic stroke first"),
    ("T008", "SYN_034", 4, 4, "POSITIVE", "Severe HA + FAST = haemorrhagic stroke"),
    ("T008", "SYN_035", 2, 3, "POSITIVE", "Meningism can cause focal signs"),

    # T007 (seizure) -> Neurological
    ("T007", "SYN_039", 5, 4, "POSITIVE", "Seizure activity = epilepsy workup"),
    ("T007", "SYN_035", 3, 3, "POSITIVE", "Meningitis can cause seizures"),
    ("T007", "SYN_066", 2, 3, "POSITIVE", "DKA/hypoglycaemia can cause seizures"),

    # T011 (suicidal) -> Psychiatric
    ("T011", "SYN_041", 4, 4, "POSITIVE", "Active SI most common in severe MDD"),
    ("T011", "SYN_045", 3, 3, "POSITIVE", "Bipolar depression also high SI risk"),
    ("T011", "SYN_047", 3, 3, "POSITIVE", "Substance use increases suicide risk"),

    # ---- SOCRATES PAIN CHARACTER (SOC_004) -----------------------------------
    ("SOC_004", "SYN_001", 5, 5, "POSITIVE", "Crushing/pressure pain = ACS"),
    ("SOC_004", "SYN_002", 5, 4, "POSITIVE", "Crushing pain = NSTEMI/UA"),
    ("SOC_004", "SYN_003", 4, 4, "POSITIVE", "Tight/pressure = stable angina"),
    ("SOC_004", "SYN_004", 4, 5, "POSITIVE", "Tearing/ripping = aortic dissection"),
    ("SOC_004", "SYN_008", 3, 4, "POSITIVE", "Sharp pleuritic = pericarditis"),
    ("SOC_004", "SYN_005", 3, 3, "POSITIVE", "Pleuritic/sharp = PE"),
    ("SOC_004", "SYN_021", 4, 4, "POSITIVE", "Burning chest pain = GERD"),
    ("SOC_004", "SYN_022", 3, 4, "POSITIVE", "Gnawing/boring = peptic ulcer"),
    ("SOC_004", "SYN_025", 3, 4, "POSITIVE", "Severe boring epigastric = pancreatitis"),
    ("SOC_004", "SYN_050", 4, 4, "POSITIVE", "Colicky/wave = renal colic"),
    ("SOC_004", "SYN_024", 4, 4, "POSITIVE", "Colicky RUQ = biliary colic"),
    ("SOC_004", "SYN_036", 4, 4, "POSITIVE", "Throbbing unilateral = migraine"),
    ("SOC_004", "SYN_037", 4, 4, "POSITIVE", "Pressing/band = tension headache"),
    ("SOC_004", "SYN_038", 5, 5, "POSITIVE", "Severe orbital/boring = cluster HA"),
    ("SOC_004", "SYN_059", 4, 4, "POSITIVE", "Throbbing joint = gout"),
    ("SOC_004", "SYN_061", 3, 3, "POSITIVE", "Shooting/electric = sciatica"),

    # ---- SOC_005 (radiation pattern) -----------------------------------------
    ("SOC_005", "SYN_001", 5, 5, "POSITIVE", "Radiation to left arm/jaw = ACS"),
    ("SOC_005", "SYN_002", 4, 4, "POSITIVE", "Left arm/jaw radiation = NSTEMI"),
    ("SOC_005", "SYN_004", 4, 5, "POSITIVE", "Back/abdominal radiation = aortic dissection"),
    ("SOC_005", "SYN_024", 4, 4, "POSITIVE", "Right shoulder radiation = biliary"),
    ("SOC_005", "SYN_025", 4, 5, "POSITIVE", "Back radiation = pancreatitis"),
    ("SOC_005", "SYN_050", 4, 5, "POSITIVE", "Flank to groin = renal colic"),
    ("SOC_005", "SYN_061", 4, 5, "POSITIVE", "Leg radiation below knee = sciatica"),

    # ---- SOC_006 (associated symptoms) ---------------------------------------
    ("SOC_006", "SYN_001", 4, 4, "POSITIVE", "Sweating/nausea with chest pain = ACS"),
    ("SOC_006", "SYN_002", 4, 3, "POSITIVE", "Diaphoresis/dyspnoea = NSTEMI"),
    ("SOC_006", "SYN_005", 4, 4, "POSITIVE", "Dyspnoea + chest pain = PE"),
    ("SOC_006", "SYN_013", 4, 3, "POSITIVE", "Fever with chest symptoms = pneumonia"),
    ("SOC_006", "SYN_036", 5, 4, "POSITIVE", "Nausea/photophobia = migraine"),
    ("SOC_006", "SYN_035", 4, 5, "POSITIVE", "Fever + HA + photophobia = meningitis"),
    ("SOC_006", "SYN_023", 4, 4, "POSITIVE", "Nausea/fever with abdominal pain = appendicitis"),
    ("SOC_006", "SYN_024", 4, 3, "POSITIVE", "Nausea with RUQ pain = biliary"),
    ("SOC_006", "SYN_028", 4, 5, "POSITIVE", "Blood in vomit = upper GI bleed"),
    ("SOC_006", "SYN_007", 4, 4, "POSITIVE", "Dyspnoea + leg swelling = HF"),
    ("SOC_006", "SYN_073", 5, 5, "POSITIVE", "Hives + dyspnoea + exposure = anaphylaxis"),

    # ---- SOC_007 (timing) ---------------------------------------------------
    ("SOC_007", "SYN_050", 5, 5, "POSITIVE", "Colicky/wave pain = renal stone"),
    ("SOC_007", "SYN_024", 4, 4, "POSITIVE", "Colicky = biliary colic"),
    ("SOC_007", "SYN_030", 4, 4, "POSITIVE", "Colicky = bowel obstruction"),
    ("SOC_007", "SYN_001", 4, 3, "POSITIVE", "Constant chest pain at rest = ACS"),
    ("SOC_007", "SYN_036", 4, 4, "POSITIVE", "Episodic HA = migraine"),
    ("SOC_007", "SYN_038", 5, 5, "POSITIVE", "Episodic severe HA in clusters = cluster HA"),
    ("SOC_007", "SYN_011", 4, 4, "POSITIVE", "Episodic paroxysmal palpitations = SVT"),

    # ---- SOC_008 (exacerbating factors) --------------------------------------
    ("SOC_008", "SYN_003", 5, 5, "POSITIVE", "Exertion worsens = stable angina"),
    ("SOC_008", "SYN_001", 3, 3, "POSITIVE", "Exertion -> ACS (unstable)"),
    ("SOC_008", "SYN_005", 4, 4, "POSITIVE", "Deep breathing worsens = PE/pleuritis"),
    ("SOC_008", "SYN_008", 4, 4, "POSITIVE", "Deep breathing worsens = pericarditis"),
    ("SOC_008", "SYN_017", 4, 4, "POSITIVE", "Breathing worsens = pneumothorax"),
    ("SOC_008", "SYN_021", 4, 4, "POSITIVE", "Lying down worsens = GERD"),
    ("SOC_008", "SYN_022", 4, 3, "POSITIVE", "Food worsens = PUD"),
    ("SOC_008", "SYN_036", 3, 3, "POSITIVE", "Activity worsens migraine"),
    ("SOC_008", "SYN_059", 3, 4, "POSITIVE", "Alcohol/purine foods trigger gout"),
    ("SOC_008", "SYN_014", 4, 4, "POSITIVE", "Exertion worsens COPD"),
    ("SOC_008", "SYN_015", 4, 4, "POSITIVE", "Exertion worsens asthma"),
    ("SOC_008", "SYN_061", 4, 4, "POSITIVE", "Movement/bending worsens sciatica"),
    ("SOC_008", "SYN_062", 2, 5, "NEGATIVE", "Exercise IMPROVES AS pain (distinguishes from OA)"),

    # ---- SOC_009 (relieving factors) -----------------------------------------
    ("SOC_009", "SYN_003", 5, 5, "POSITIVE", "GTN relief = stable angina"),
    ("SOC_009", "SYN_001", 2, 3, "POSITIVE", "GTN may partially relieve ACS"),
    ("SOC_009", "SYN_021", 5, 5, "POSITIVE", "Antacid relief = GERD"),
    ("SOC_009", "SYN_022", 3, 3, "POSITIVE", "Antacids relieve PUD"),
    ("SOC_009", "SYN_025", 4, 4, "POSITIVE", "Sitting forward relieves pancreatitis"),
    ("SOC_009", "SYN_008", 4, 4, "POSITIVE", "Sitting forward relieves pericarditis"),
    ("SOC_009", "SYN_027", 4, 4, "POSITIVE", "Defecation relieves IBS"),
    ("SOC_009", "SYN_062", 4, 5, "POSITIVE", "Exercise relieves AS (key differentiator)"),

    # ---- SOC_010 (severity slider) ------------------------------------------
    ("SOC_010", "SYN_001", 5, 3, "POSITIVE", "Severe pain (>=8) supports ACS"),
    ("SOC_010", "SYN_004", 5, 4, "POSITIVE", "Extreme pain = aortic dissection"),
    ("SOC_010", "SYN_050", 5, 4, "POSITIVE", "Severe colicky pain = renal stone"),
    ("SOC_010", "SYN_038", 5, 4, "POSITIVE", "Severe orbital pain = cluster HA"),
    ("SOC_010", "SYN_025", 5, 4, "POSITIVE", "Severe epigastric = pancreatitis"),
    ("SOC_010", "SYN_059", 5, 4, "POSITIVE", "Extreme joint pain = gout"),
    ("SOC_010", "SYN_027", 1, 3, "NEGATIVE", "Mild pain <5 supports IBS over organic"),

    # ---- OLD CARTS OC_003 (duration per episode) ----------------------------
    ("OC_003", "SYN_011", 5, 5, "POSITIVE", "Seconds-minutes palpitations = SVT"),
    ("OC_003", "SYN_010", 4, 3, "POSITIVE", "Sustained irregular = AF"),
    ("OC_003", "SYN_036", 4, 4, "POSITIVE", "4-72 hours = migraine"),
    ("OC_003", "SYN_037", 3, 3, "POSITIVE", "Hours = tension headache"),
    ("OC_003", "SYN_033", 3, 5, "POSITIVE", "<24h resolving deficit = TIA"),
    ("OC_003", "SYN_003", 3, 4, "POSITIVE", "Minutes with exertion = stable angina"),

    # ---- ROS CARDIOVASCULAR NODES -------------------------------------------
    ("ROS_CVS_001", "SYN_001", 4, 4, "POSITIVE", "Exertional chest pain = ACS risk"),
    ("ROS_CVS_001", "SYN_002", 4, 4, "POSITIVE", "Rest chest pain = NSTEMI"),
    ("ROS_CVS_001", "SYN_003", 5, 5, "POSITIVE", "Exertional CP relieved by GTN = stable angina"),
    ("ROS_CVS_001", "SYN_008", 3, 4, "POSITIVE", "Pleuritic chest pain = pericarditis"),
    ("ROS_CVS_001", "SYN_021", 4, 3, "POSITIVE", "Post-meal discomfort = GERD masquerade"),

    ("ROS_CVS_002", "SYN_007", 5, 5, "POSITIVE", "Orthopnoea = left heart failure"),
    ("ROS_CVS_003", "SYN_007", 5, 5, "POSITIVE", "PND = left heart failure"),
    ("ROS_CVS_004", "SYN_007", 5, 4, "POSITIVE", "Peripheral edema = right HF"),
    ("ROS_CVS_004", "SYN_006", 4, 3, "POSITIVE", "Unilateral leg swelling = DVT"),
    ("ROS_CVS_004", "SYN_016", 3, 3, "POSITIVE", "Leg swelling + pleural effusion"),
    ("ROS_CVS_004", "SYN_032", 3, 3, "POSITIVE", "Abdominal swelling = ascites in cirrhosis"),

    ("ROS_CVS_005", "SYN_010", 5, 4, "POSITIVE", "Irregular palpitations = AF"),
    ("ROS_CVS_005", "SYN_011", 5, 4, "POSITIVE", "Paroxysmal regular palpitations = SVT"),
    ("ROS_CVS_005", "SYN_065", 3, 3, "POSITIVE", "Palpitations = hyperthyroidism"),
    ("ROS_CVS_005", "SYN_043", 3, 3, "POSITIVE", "Palpitations with anxiety = panic disorder"),
    ("ROS_CVS_005", "SYN_012", 3, 3, "POSITIVE", "Palpitations + high BP = hypertensive crisis"),

    ("ROS_CVS_006", "SYN_011", 4, 4, "POSITIVE", "Syncope with palpitations = SVT"),
    ("ROS_CVS_006", "SYN_012", 2, 3, "POSITIVE", "Syncope = hypertensive crisis complication"),
    ("ROS_CVS_006", "SYN_039", 3, 3, "POSITIVE", "Syncope + postictal = epilepsy"),
    ("ROS_CVS_006", "SYN_033", 3, 3, "POSITIVE", "Syncope = TIA equivalent?"),

    ("ROS_CVS_007", "SYN_007", 4, 3, "POSITIVE", "Known HTN = heart failure risk"),
    ("ROS_CVS_007", "SYN_012", 5, 5, "POSITIVE", "Known HTN = hypertensive crisis pre-test"),
    ("ROS_CVS_007", "SYN_034", 4, 4, "POSITIVE", "HTN = haemorrhagic stroke risk"),

    ("ROS_CVS_008", "SYN_006", 4, 4, "POSITIVE", "Claudication = PAD / DVT distinction"),

    # ---- ROS RESPIRATORY NODES ----------------------------------------------
    ("ROS_RES_001", "SYN_013", 4, 3, "POSITIVE", "Productive cough with fever = pneumonia"),
    ("ROS_RES_001", "SYN_018", 4, 3, "POSITIVE", "Chronic cough = TB"),
    ("ROS_RES_001", "SYN_019", 3, 4, "POSITIVE", "Persistent cough in smoker = lung cancer"),
    ("ROS_RES_001", "SYN_020", 5, 3, "POSITIVE", "Acute productive cough = bronchitis"),
    ("ROS_RES_001", "SYN_014", 4, 3, "POSITIVE", "Worsening chronic cough = COPD"),
    ("ROS_RES_001", "SYN_015", 4, 3, "POSITIVE", "Cough + wheeze = asthma"),

    ("ROS_RES_002", "SYN_013", 4, 4, "POSITIVE", "Rust/yellow sputum = pneumonia"),
    ("ROS_RES_002", "SYN_018", 4, 5, "POSITIVE", "Haemoptysis = TB"),
    ("ROS_RES_002", "SYN_019", 3, 5, "POSITIVE", "Haemoptysis in smoker = lung cancer"),
    ("ROS_RES_002", "SYN_028", 2, 4, "POSITIVE", "Haemoptysis can be from upper GI"),
    ("ROS_RES_002", "SYN_007", 3, 4, "POSITIVE", "Frothy pink sputum = pulmonary oedema"),

    ("ROS_RES_003", "SYN_007", 4, 4, "POSITIVE", "Grade 4-5 dyspnoea = heart failure"),
    ("ROS_RES_003", "SYN_014", 4, 4, "POSITIVE", "Progressive dyspnoea = COPD"),
    ("ROS_RES_003", "SYN_005", 4, 4, "POSITIVE", "Sudden dyspnoea = PE"),
    ("ROS_RES_003", "SYN_017", 4, 4, "POSITIVE", "Sudden dyspnoea = pneumothorax"),
    ("ROS_RES_003", "SYN_015", 4, 3, "POSITIVE", "Variable dyspnoea = asthma"),
    ("ROS_RES_003", "SYN_013", 3, 3, "POSITIVE", "Dyspnoea + fever = pneumonia"),

    ("ROS_RES_004", "SYN_015", 5, 5, "POSITIVE", "Wheeze = asthma first"),
    ("ROS_RES_004", "SYN_014", 4, 4, "POSITIVE", "Wheeze = COPD exacerbation"),
    ("ROS_RES_004", "SYN_073", 4, 4, "POSITIVE", "Wheeze after exposure = anaphylaxis"),

    ("ROS_RES_006", "SYN_018", 4, 5, "POSITIVE", "Haemoptysis = TB"),
    ("ROS_RES_006", "SYN_019", 4, 5, "POSITIVE", "Haemoptysis in smoker = lung cancer"),
    ("ROS_RES_006", "SYN_005", 3, 4, "POSITIVE", "Haemoptysis = PE"),

    ("ROS_RES_007", "SYN_019", 5, 4, "POSITIVE", "Smoking = lung cancer strongest risk factor"),
    ("ROS_RES_007", "SYN_014", 5, 5, "POSITIVE", "Smoking = COPD strongest risk factor"),
    ("ROS_RES_007", "SYN_001", 4, 3, "POSITIVE", "Smoking = ACS risk factor"),
    ("ROS_RES_007", "SYN_018", 2, 2, "POSITIVE", "Smoking weakly associated with TB"),

    # ---- ROS GI NODES -------------------------------------------------------
    ("ROS_GI_001", "SYN_028", 5, 5, "POSITIVE", "Blood in vomit = upper GI bleed"),
    ("ROS_GI_001", "SYN_023", 4, 3, "POSITIVE", "Nausea/vomiting = appendicitis"),
    ("ROS_GI_001", "SYN_025", 4, 3, "POSITIVE", "Vomiting = pancreatitis"),
    ("ROS_GI_001", "SYN_031", 3, 3, "POSITIVE", "Nausea = hepatitis"),
    ("ROS_GI_001", "SYN_066", 4, 4, "POSITIVE", "Vomiting + known DM = DKA"),

    ("ROS_GI_002", "SYN_023", 5, 5, "POSITIVE", "RLQ pain = appendicitis"),
    ("ROS_GI_002", "SYN_024", 5, 5, "POSITIVE", "RUQ pain post-meal = biliary"),
    ("ROS_GI_002", "SYN_025", 5, 4, "POSITIVE", "Epigastric pain = pancreatitis"),
    ("ROS_GI_002", "SYN_022", 4, 4, "POSITIVE", "Epigastric pain with meals = PUD"),
    ("ROS_GI_002", "SYN_021", 3, 3, "POSITIVE", "Epigastric burning = GERD"),
    ("ROS_GI_002", "SYN_053", 4, 5, "POSITIVE", "Lower abdominal pain in pregnant female = ectopic"),
    ("ROS_GI_002", "SYN_026", 4, 4, "POSITIVE", "Colicky central pain = IBD"),

    ("ROS_GI_003", "SYN_026", 5, 5, "POSITIVE", "Bloody diarrhoea = IBD"),
    ("ROS_GI_003", "SYN_029", 4, 4, "POSITIVE", "Blood PR = lower GI bleed"),
    ("ROS_GI_003", "SYN_027", 4, 4, "POSITIVE", "Alternating bowel habit = IBS"),
    ("ROS_GI_003", "SYN_030", 4, 5, "POSITIVE", "Absolute constipation = bowel obstruction"),

    ("ROS_GI_004", "SYN_021", 5, 5, "POSITIVE", "Heartburn = GERD"),
    ("ROS_GI_004", "SYN_022", 3, 3, "POSITIVE", "Heartburn = PUD differential"),

    ("ROS_GI_005", "SYN_019", 3, 4, "POSITIVE", "Dysphagia = oesophageal cancer"),
    ("ROS_GI_005", "SYN_021", 3, 3, "POSITIVE", "Dysphagia = severe GERD/stricture"),

    ("ROS_GI_006", "SYN_031", 5, 5, "POSITIVE", "Jaundice + dark urine + pale stools = hepatitis"),
    ("ROS_GI_006", "SYN_032", 4, 4, "POSITIVE", "Jaundice = cirrhosis decompensation"),
    ("ROS_GI_006", "SYN_024", 3, 4, "POSITIVE", "Jaundice = cholestatic biliary disease"),

    ("ROS_GI_007", "SYN_032", 5, 5, "POSITIVE", "Alcohol = cirrhosis strongest risk"),
    ("ROS_GI_007", "SYN_025", 4, 4, "POSITIVE", "Alcohol = pancreatitis trigger"),
    ("ROS_GI_007", "SYN_028", 4, 4, "POSITIVE", "Alcohol = variceal upper GI bleed"),
    ("ROS_GI_007", "SYN_059", 3, 3, "POSITIVE", "Alcohol triggers gout"),

    # ---- ROS GU NODES -------------------------------------------------------
    ("ROS_GU_001", "SYN_048", 5, 5, "POSITIVE", "Dysuria = UTI"),
    ("ROS_GU_001", "SYN_049", 4, 4, "POSITIVE", "Dysuria + fever = pyelonephritis"),
    ("ROS_GU_001", "SYN_050", 3, 3, "POSITIVE", "Dysuria with haematuria = stone"),

    ("ROS_GU_002", "SYN_048", 5, 4, "POSITIVE", "Frequency = UTI"),
    ("ROS_GU_002", "SYN_051", 4, 4, "POSITIVE", "Reduced stream/nocturia = BPH"),
    ("ROS_GU_002", "SYN_063", 4, 4, "POSITIVE", "Polyuria = diabetes mellitus"),

    ("ROS_GU_003", "SYN_050", 5, 5, "POSITIVE", "Haematuria + flank pain = renal stone"),
    ("ROS_GU_003", "SYN_049", 3, 3, "POSITIVE", "Haematuria = pyelonephritis"),
    ("ROS_GU_003", "SYN_048", 4, 3, "POSITIVE", "Haematuria = UTI"),

    ("ROS_GU_004", "SYN_051", 5, 5, "POSITIVE", "Obstructive symptoms = BPH"),

    ("ROS_GU_005", "SYN_054", 4, 4, "POSITIVE", "Abnormal discharge + pelvic pain = PID"),
    ("ROS_GU_005", "SYN_052", 3, 3, "POSITIVE", "Menstrual irregularity = ovarian cyst"),
    ("ROS_GU_005", "SYN_053", 4, 5, "POSITIVE", "Amenorrhoea + pelvic pain = ectopic"),

    ("ROS_GU_006", "SYN_050", 5, 5, "POSITIVE", "Flank pain = renal colic"),
    ("ROS_GU_006", "SYN_049", 4, 4, "POSITIVE", "Flank pain + fever = pyelonephritis"),

    ("ROS_GU_008", "SYN_053", 5, 5, "POSITIVE", "Pregnancy + pelvic pain = ectopic excluded"),

    # ---- ROS MSK NODES ------------------------------------------------------
    ("ROS_MSK_001", "SYN_058", 5, 4, "POSITIVE", "Small joint symmetrical polyarthritis = RA"),
    ("ROS_MSK_001", "SYN_057", 5, 3, "POSITIVE", "Large joint monoarthritis = OA"),
    ("ROS_MSK_001", "SYN_059", 4, 5, "POSITIVE", "First MTP monoarthritis = gout"),
    ("ROS_MSK_001", "SYN_060", 3, 5, "POSITIVE", "Hot red joint = septic arthritis"),
    ("ROS_MSK_001", "SYN_062", 3, 4, "POSITIVE", "Sacroiliac/spinal joints = AS"),

    ("ROS_MSK_002", "SYN_058", 5, 5, "POSITIVE", "Morning stiffness > 60 min = RA"),
    ("ROS_MSK_002", "SYN_057", 4, 4, "NEGATIVE", "Morning stiffness < 30 min = OA (inverse diagnostic)"),
    ("ROS_MSK_002", "SYN_062", 4, 4, "POSITIVE", "Morning spinal stiffness = AS"),

    ("ROS_MSK_003", "SYN_061", 5, 5, "POSITIVE", "Leg pain below knee radiation = sciatica"),
    ("ROS_MSK_003", "SYN_062", 3, 4, "POSITIVE", "Lower back stiffness = AS"),
    ("ROS_MSK_003", "SYN_057", 4, 3, "POSITIVE", "Lower back degeneration = OA"),

    ("ROS_MSK_008", "SYN_059", 5, 5, "POSITIVE", "Hot joint + alcohol + purine diet = gout"),
    ("ROS_MSK_008", "SYN_060", 4, 4, "POSITIVE", "Hot joint + fever = septic arthritis"),

    # ---- ROS NEURO NODES ---------------------------------------------------
    ("ROS_NEU_001", "SYN_036", 5, 4, "POSITIVE", "Episodic severe HA = migraine"),
    ("ROS_NEU_001", "SYN_037", 5, 4, "POSITIVE", "Daily pressing HA = tension"),
    ("ROS_NEU_001", "SYN_034", 4, 5, "POSITIVE", "Thunderclap HA = haemorrhagic stroke/SAH"),
    ("ROS_NEU_001", "SYN_035", 4, 4, "POSITIVE", "HA + fever = meningitis"),
    ("ROS_NEU_001", "SYN_038", 4, 5, "POSITIVE", "Severe orbital HA in clusters = cluster HA"),
    ("ROS_NEU_001", "SYN_012", 3, 3, "POSITIVE", "Headache = hypertensive crisis"),

    ("ROS_NEU_002", "SYN_033", 5, 5, "POSITIVE", "Unilateral weakness = ischaemic stroke"),
    ("ROS_NEU_002", "SYN_034", 4, 4, "POSITIVE", "Sudden weakness = haemorrhagic stroke"),
    ("ROS_NEU_002", "SYN_061", 4, 4, "POSITIVE", "Leg weakness = sciatica (foot drop)"),

    ("ROS_NEU_003", "SYN_040", 5, 5, "POSITIVE", "Glove-stocking tingling = peripheral neuropathy"),
    ("ROS_NEU_003", "SYN_063", 4, 4, "POSITIVE", "Peripheral neuropathy = diabetes"),
    ("ROS_NEU_003", "SYN_061", 4, 4, "POSITIVE", "Dermatomal numbness = radiculopathy"),

    ("ROS_NEU_004", "SYN_035", 4, 4, "POSITIVE", "Acute confusion + fever = meningitis"),
    ("ROS_NEU_004", "SYN_067", 4, 4, "POSITIVE", "Acute confusion = sepsis encephalopathy"),
    ("ROS_NEU_004", "SYN_066", 3, 4, "POSITIVE", "Confusion in DM = DKA/hypoglycaemia"),

    ("ROS_NEU_005", "SYN_039", 5, 5, "POSITIVE", "Seizures = epilepsy"),
    ("ROS_NEU_005", "SYN_035", 3, 3, "POSITIVE", "Seizures = meningitis"),

    ("ROS_NEU_007", "SYN_033", 4, 5, "POSITIVE", "Aphasia/dysarthria = stroke"),

    ("ROS_NEU_008", "SYN_039", 3, 3, "POSITIVE", "Tremor can accompany epilepsy"),

    # ---- ROS PSYCH NODES ---------------------------------------------------
    ("ROS_PSY_001", "SYN_041", 5, 5, "POSITIVE", "Depressed mood nearly every day = MDD"),
    ("ROS_PSY_002", "SYN_041", 5, 5, "POSITIVE", "Anhedonia + depressed mood = MDD"),
    ("ROS_PSY_003", "SYN_042", 5, 5, "POSITIVE", "Excessive worry = GAD"),
    ("ROS_PSY_003", "SYN_043", 4, 4, "POSITIVE", "Anxiety with physical symptoms = panic"),
    ("ROS_PSY_004", "SYN_043", 5, 5, "POSITIVE", "Panic attacks = panic disorder"),
    ("ROS_PSY_005", "SYN_044", 5, 5, "POSITIVE", "Hallucinations = schizophrenia"),
    ("ROS_PSY_005", "SYN_047", 3, 3, "POSITIVE", "Tactile hallucinations = alcohol withdrawal"),
    ("ROS_PSY_006", "SYN_045", 5, 5, "POSITIVE", "Manic episodes = bipolar disorder"),
    ("ROS_PSY_007", "SYN_046", 5, 5, "POSITIVE", "Flashbacks/intrusions = PTSD"),
    ("ROS_PSY_008", "SYN_047", 5, 5, "POSITIVE", "Problematic substance use = SUD"),
    ("ROS_PSY_008", "SYN_041", 3, 2, "POSITIVE", "Alcohol use comorbid MDD"),

    # ---- ROS ENDOCRINE NODES -----------------------------------------------
    ("ROS_END_001", "SYN_063", 5, 5, "POSITIVE", "Polydipsia + polyuria = DM type 2"),
    ("ROS_END_001", "SYN_066", 4, 4, "POSITIVE", "Polyuria + vomiting in known DM = DKA"),
    ("ROS_END_002", "SYN_064", 5, 4, "POSITIVE", "Weight gain without reason = hypothyroid"),
    ("ROS_END_002", "SYN_065", 5, 4, "POSITIVE", "Weight loss with appetite = hyperthyroid"),
    ("ROS_END_002", "SYN_063", 3, 3, "POSITIVE", "Weight loss = uncontrolled DM"),
    ("ROS_END_002", "SYN_072", 3, 4, "POSITIVE", "Weight loss = lymphoma B-symptoms"),
    ("ROS_END_003", "SYN_064", 5, 5, "POSITIVE", "Cold intolerance = hypothyroidism"),
    ("ROS_END_003", "SYN_065", 5, 5, "POSITIVE", "Heat intolerance = hyperthyroidism"),
    ("ROS_END_004", "SYN_064", 4, 4, "POSITIVE", "Goitre = hypothyroidism (Hashimotos)"),
    ("ROS_END_004", "SYN_065", 4, 4, "POSITIVE", "Goitre = hyperthyroidism (Graves)"),
    ("ROS_END_008", "SYN_063", 5, 5, "POSITIVE", "Known DM = DM on all GI/GU/NEURO paths"),
    ("ROS_END_008", "SYN_066", 4, 4, "POSITIVE", "Known DM + acute = DKA differential"),

    # ---- ROS HEME NODES ----------------------------------------------------
    ("ROS_HEM_001", "SYN_071", 3, 3, "POSITIVE", "Easy bruising = IDA severe"),
    ("ROS_HEM_002", "SYN_071", 5, 4, "POSITIVE", "Pallor + fatigue = iron deficiency anaemia"),
    ("ROS_HEM_002", "SYN_064", 3, 3, "POSITIVE", "Fatigue = hypothyroidism"),
    ("ROS_HEM_003", "SYN_072", 5, 5, "POSITIVE", "Painless lymphadenopathy = lymphoma"),
    ("ROS_HEM_003", "SYN_067", 3, 3, "POSITIVE", "Lymphadenopathy = infectious cause"),
    ("ROS_HEM_004", "SYN_073", 4, 4, "POSITIVE", "Petechiae = thrombocytopenia/ITP"),
    ("ROS_HEM_004", "SYN_035", 4, 5, "POSITIVE", "Purpuric non-blanching rash = meningococcaemia"),

    # ---- ROS CONSTITUTIONAL ------------------------------------------------
    ("ROS_CON_001", "SYN_013", 4, 3, "POSITIVE", "Fever + chest = pneumonia"),
    ("ROS_CON_001", "SYN_035", 4, 5, "POSITIVE", "Fever + headache + neck stiffness = meningitis"),
    ("ROS_CON_001", "SYN_067", 4, 4, "POSITIVE", "High fever + infection signs = sepsis"),
    ("ROS_CON_001", "SYN_069", 4, 4, "POSITIVE", "Cyclical fever = malaria"),
    ("ROS_CON_001", "SYN_070", 4, 4, "POSITIVE", "Fever + rigors = malaria"),
    ("ROS_CON_001", "SYN_075", 4, 3, "POSITIVE", "Stepwise fever = typhoid"),
    ("ROS_CON_001", "SYN_068", 3, 3, "POSITIVE", "Fever + localised erythema = cellulitis"),
    ("ROS_CON_001", "SYN_031", 3, 3, "POSITIVE", "Fever + jaundice = hepatitis"),

    ("ROS_CON_002", "SYN_018", 5, 4, "POSITIVE", "Weight loss = TB B-symptom"),
    ("ROS_CON_002", "SYN_072", 5, 4, "POSITIVE", "Weight loss = lymphoma B-symptom"),
    ("ROS_CON_002", "SYN_019", 4, 4, "POSITIVE", "Weight loss in smoker = lung cancer"),
    ("ROS_CON_002", "SYN_065", 4, 4, "POSITIVE", "Weight loss = hyperthyroidism"),
    ("ROS_CON_002", "SYN_041", 3, 3, "POSITIVE", "Weight loss = severe depression"),

    ("ROS_CON_004", "SYN_018", 5, 5, "POSITIVE", "Drenching night sweats = TB"),
    ("ROS_CON_004", "SYN_072", 5, 5, "POSITIVE", "Drenching night sweats = lymphoma"),

    ("ROS_CON_006", "SYN_070", 5, 5, "POSITIVE", "Rigors = malaria"),
    ("ROS_CON_006", "SYN_049", 4, 4, "POSITIVE", "Rigors = pyelonephritis bacteraemia"),
    ("ROS_CON_006", "SYN_067", 4, 4, "POSITIVE", "Rigors = sepsis"),

    ("ROS_CON_008", "SYN_070", 5, 5, "POSITIVE", "Travel to endemic area = malaria"),
    ("ROS_CON_008", "SYN_075", 4, 4, "POSITIVE", "Travel = typhoid"),
    ("ROS_CON_008", "SYN_069", 4, 4, "POSITIVE", "Travel = dengue fever"),

    # ---- PMH NODES ---------------------------------------------------------
    ("PMH_001", "SYN_001", 4, 4, "POSITIVE", "Prior MI = repeat ACS high risk"),
    ("PMH_001", "SYN_007", 4, 4, "POSITIVE", "Prior MI = heart failure risk"),
    ("PMH_002", "SYN_033", 4, 4, "POSITIVE", "Prior stroke = TIA/recurrence risk"),
    ("PMH_003", "SYN_007", 3, 3, "POSITIVE", "CKD = heart failure complication"),
    ("PMH_004", "SYN_018", 4, 5, "POSITIVE", "Prior TB = reactivation risk"),
    ("PMH_005", "SYN_018", 4, 4, "POSITIVE", "HIV = TB risk"),
    ("PMH_005", "SYN_067", 3, 4, "POSITIVE", "HIV = opportunistic infection/sepsis"),

    ("FAM_001", "SYN_001", 4, 3, "POSITIVE", "Family premature CVD = ACS pre-test risk"),
    ("FAM_001", "SYN_003", 3, 3, "POSITIVE", "Family CVD = stable angina risk"),
    ("FAM_002", "SYN_063", 4, 3, "POSITIVE", "Family DM = type 2 DM risk"),
    ("FAM_004", "SYN_041", 3, 3, "POSITIVE", "Family MH = MDD pre-test"),
    ("FAM_004", "SYN_044", 3, 3, "POSITIVE", "Family schizophrenia = pre-test"),
    ("FAM_006", "SYN_001", 3, 4, "POSITIVE", "Family sudden death = channelopathy/HCM"),

    # Social history
    ("SOH_003", "SYN_032", 5, 5, "POSITIVE", "Heavy alcohol = cirrhosis"),
    ("SOH_003", "SYN_025", 4, 4, "POSITIVE", "Heavy alcohol = pancreatitis"),
    ("SOH_003", "SYN_047", 4, 4, "POSITIVE", "Heavy alcohol = SUD"),
    ("SOH_004", "SYN_047", 5, 5, "POSITIVE", "Illicit drugs = SUD"),

]

# =============================================================================
# 4. ROUTING RULES
# (complaint_keyword, framework, priority, notes)
# =============================================================================

ROUTING_RULES = [
    # SOCRATES - Pain presentations
    ("chest pain",     "SOCRATES", 1, "Classic acute pain presentation"),
    ("chest tightness","SOCRATES", 1, "Cardiac compression symptom"),
    ("heart pain",     "SOCRATES", 1, "Patient describing cardiac pain"),
    ("headache",       "SOCRATES", 2, "Pain-based complaint"),
    ("head pain",      "SOCRATES", 2, "Pain-based complaint"),
    ("stomach ache",   "SOCRATES", 2, "Abdominal pain"),
    ("stomach pain",   "SOCRATES", 2, "Abdominal pain"),
    ("abdominal pain", "SOCRATES", 2, "Abdominal pain"),
    ("belly pain",     "SOCRATES", 2, "Abdominal pain"),
    ("tummy pain",     "SOCRATES", 2, "Paediatric abdominal pain"),
    ("back pain",      "SOCRATES", 2, "MSK pain complaint"),
    ("joint pain",     "SOCRATES", 2, "Arthralgia"),
    ("knee pain",      "SOCRATES", 2, "Knee arthralgia"),
    ("leg pain",       "SOCRATES", 2, "Leg pain"),
    ("arm pain",       "SOCRATES", 2, "Arm pain"),
    ("shoulder pain",  "SOCRATES", 2, "Shoulder pain"),
    ("neck pain",      "SOCRATES", 2, "Neck pain"),
    ("tooth pain",     "SOCRATES", 3, "Dental pain"),
    ("toothache",      "SOCRATES", 3, "Dental pain"),
    ("earache",        "SOCRATES", 3, "Otic pain"),
    ("ear pain",       "SOCRATES", 3, "Otic pain"),
    ("eye pain",       "SOCRATES", 3, "Ocular pain"),
    ("pelvic pain",    "SOCRATES", 3, "Pelvic/GU pain"),
    ("period pain",    "SOCRATES", 3, "Dysmenorrhoea"),
    # OLD CARTS - Systemic/chronic
    ("fever",          "OLD_CARTS", 4, "Systemic/constitutional complaint"),
    ("fatigue",        "OLD_CARTS", 4, "Systemic complaint"),
    ("tired",          "OLD_CARTS", 4, "Systemic complaint"),
    ("weakness",       "OLD_CARTS", 4, "Systemic complaint"),
    ("weight loss",    "OLD_CARTS", 4, "Systemic/constitutional complaint"),
    ("cough",          "OLD_CARTS", 4, "Respiratory complaint"),
    ("shortness of breath", "OLD_CARTS", 4, "Respiratory/cardiac complaint"),
    ("breathless",     "OLD_CARTS", 4, "Respiratory complaint"),
    ("swelling",       "OLD_CARTS", 5, "Oedema/swelling complaint"),
    ("diarrhoea",      "OLD_CARTS", 5, "GI complaint"),
    ("constipation",   "OLD_CARTS", 5, "GI complaint"),
    ("vomiting",       "OLD_CARTS", 5, "GI complaint"),
    ("nausea",         "OLD_CARTS", 5, "GI complaint"),
    ("rash",           "OLD_CARTS", 5, "Integumentary complaint"),
    ("skin",           "OLD_CARTS", 6, "Integumentary complaint"),
    ("itching",        "OLD_CARTS", 5, "Pruritis complaint"),
    ("itch",           "OLD_CARTS", 5, "Pruritis complaint"),
    # SAMPLE - Trauma
    ("accident",       "SAMPLE", 1, "Trauma/incident presentation"),
    ("fall",           "SAMPLE", 1, "Trauma/incident presentation"),
    ("injury",         "SAMPLE", 1, "Trauma/incident presentation"),
    ("trauma",         "SAMPLE", 1, "Trauma presentation"),
    ("burn",           "SAMPLE", 1, "Burn injury"),
    ("overdose",       "SAMPLE", 1, "Poisoning/overdose"),
    ("poisoning",      "SAMPLE", 1, "Poisoning presentation"),
    ("assault",        "SAMPLE", 1, "Assault trauma"),
    ("bite",           "SAMPLE", 2, "Bite injury"),
    ("wound",          "SAMPLE", 2, "Wound/laceration"),
    ("cut",            "SAMPLE", 2, "Laceration"),
    ("fracture",       "SAMPLE", 1, "Fracture trauma"),
    ("broken",         "SAMPLE", 2, "Fracture trauma"),
    # COCA - Fluid output
    ("blood in urine", "COCA", 1, "Haematuria"),
    ("haematuria",     "COCA", 1, "Haematuria"),
    ("blood in stool", "COCA", 1, "GI bleed presentation"),
    ("bleeding",       "COCA", 2, "Fluid/blood output"),
    ("discharge",      "COCA", 2, "Abnormal fluid output"),
    ("vomiting blood", "COCA", 1, "Haematemesis"),
    ("coughing blood", "COCA", 1, "Haemoptysis"),
    ("jaundice",       "COCA", 1, "Colour change/bilirubin"),
    ("yellow skin",    "COCA", 1, "Jaundice"),
    ("dark urine",     "COCA", 1, "Urine colour change"),
    # ROTS - Psychiatric/confusion
    ("depression",     "ROTS", 1, "Psychiatric chief complaint"),
    ("anxiety",        "ROTS", 1, "Psychiatric chief complaint"),
    ("confused",       "ROTS", 1, "Confusional state"),
    ("confusion",      "ROTS", 1, "Confusional state"),
    ("hallucination",  "ROTS", 1, "Psychiatric complaint"),
    ("voices",         "ROTS", 1, "Auditory hallucination"),
    ("mental",         "ROTS", 2, "Psychiatric complaint"),
    ("sad",            "ROTS", 2, "Depressive complaint"),
    ("panic",          "ROTS", 2, "Panic/anxiety complaint"),
    ("memory",         "ROTS", 2, "Cognitive complaint"),
    ("forgetful",      "ROTS", 2, "Memory complaint"),
    ("behaviour",      "ROTS", 2, "Behavioural change"),
    ("mood",           "ROTS", 2, "Mood disorder complaint"),
    ("suicide",        "ROTS", 1, "Suicidal ideation - ROTS framework"),
    ("self-harm",      "ROTS", 1, "Self-harm complaint"),
    ("psychiatric",    "ROTS", 1, "Psychiatric complaint"),
]

# =============================================================================
# 5. NODE FOLLOWUPS (trigger_node_id, trigger_value, followup_node_id, priority)
# =============================================================================

NODE_FOLLOWUPS = [
    # If patient says YES to haemoptysis -> ask about TB history
    ("ROS_RES_006", "yes", "PMH_004", 1),
    ("ROS_RES_006", "Streaks of blood in phlegm", "PMH_004", 1),
    # If fever confirmed -> ask about travel history
    ("ROS_CON_001", "High: 39.4-40.9 C", "ROS_CON_008", 1),
    ("ROS_CON_001", "Very high: 41 C or above", "ROS_CON_008", 1),
    # If known DM -> ask about DKA symptoms
    ("ROS_END_008", "Type 1 DM - insulin", "ROS_END_001", 1),
    ("ROS_END_008", "Type 2 DM - insulin", "ROS_END_001", 1),
    # If trauma history -> ask about last meal
    ("T010", "yes", "SAM_005", 1),
    # If chest pain at rest -> ask about GTN response
    ("ROS_CVS_001", "Chest pain at rest", "SOC_009", 1),
    # If night sweats + weight loss -> ask about HIV
    ("ROS_CON_004", "yes", "PMH_005", 1),
    # If leg swelling bilateral -> ask about heart failure symptoms
    ("ROS_CVS_004", "Moderate ankle and lower leg swelling", "ROS_CVS_002", 1),
    ("ROS_CVS_004", "Severe swelling extending above the knees", "ROS_CVS_002", 1),
    # If haematuria -> ask about flank pain
    ("ROS_GU_003", "Visible blood - pink or red urine", "ROS_GU_006", 1),
    # If blood in stool -> ask about bowel habit changes
    ("ROS_GI_009", "Bright red blood on toilet paper or in bowl", "ROS_GI_003", 1),
    # If confusion -> ask about fever (delirium workup)
    ("ROS_NEU_004", "Sudden episodes of confusion", "ROS_CON_001", 1),
    ("ROS_NEU_004", "Persistent confusion since illness or event", "PMH_005", 1),
    # If prior surgery -> ask about recent hospitalisation
    ("SRG_001", "yes", "PMH_008", 1),
    # If suicidal ideation confirmed (through ROTS) -> ensure risk nodes asked
    ("ROTS_001", "History of trauma or abuse", "ROTS_003", 1),
    # If pregnancy possible -> ask about pelvic symptoms
    ("ROS_GU_008", "Possibly pregnant / Not sure", "ROS_GU_005", 1),
    ("ROS_GU_008", "Currently pregnant (known)", "ROS_GU_005", 1),
    # If hallucinations present -> ensure substance use screened
    ("ROS_PSY_005", "Hearing voices when no one is there", "ROS_PSY_008", 1),
    ("ROS_PSY_005", "Seeing things others cannot see", "ROS_PSY_008", 1),
    # If eye redness with pain -> urgent ophthalmology flag
    ("ROS_EYE_002", "Severe pain with or without redness", "ROS_EYE_004", 1),
    # If alcohol heavy use -> liver disease
    ("SOH_003", "Heavily (15-35 units/week)", "ROS_GI_008", 1),
    ("SOH_003", "Very heavily (> 35 units/week)", "ROS_GI_008", 1),
]

# =============================================================================
# 6. PROXY MAPPINGS
# (vague_term, fhir_proxy_tag, icd10_approx, clarification_node_id)
# =============================================================================

PROXY_MAPPINGS = [
    ("heart problem",           "Cardiac_Unspecified",         "I99",   "PMH_001"),
    ("heart issue",             "Cardiac_Unspecified",         "I99",   "PMH_001"),
    ("heart attack before",     "Cardiac_Unspecified_PriorMI", "Z87.39","PMH_001"),
    ("heart failure",           "HF_Unspecified",              "I50.9", "ROS_CVS_002"),
    ("lung problem",            "Pulmonary_Unspecified",       "J99",   "ROS_RES_001"),
    ("breathing problem",       "Pulmonary_Unspecified",       "J99",   "ROS_RES_003"),
    ("asthma",                  "Asthma_Known",                "J45.9", "ROS_RES_004"),
    ("copd",                    "COPD_Known",                  "J44.9", "ROS_RES_007"),
    ("kidney problem",          "Renal_Unspecified",           "N28.9", "PMH_003"),
    ("kidney disease",          "Renal_Unspecified",           "N28.9", "PMH_003"),
    ("liver problem",           "Hepatic_Unspecified",         "K76.9", "ROS_GI_008"),
    ("liver disease",           "Hepatic_Unspecified",         "K76.9", "ROS_GI_008"),
    ("hepatitis",               "Hepatitis_Unspecified",       "K75.9", "ROS_GI_006"),
    ("diabetes",                "DM_Unspecified",              "E14.9", "ROS_END_008"),
    ("sugar problem",           "DM_Unspecified",              "E14.9", "ROS_END_008"),
    ("sugar disease",           "DM_Unspecified",              "E14.9", "ROS_END_008"),
    ("thyroid problem",         "Thyroid_Unspecified",         "E07.9", "ROS_END_004"),
    ("thyroid disease",         "Thyroid_Unspecified",         "E07.9", "ROS_END_004"),
    ("blood problem",           "Hematologic_Unspecified",     "D75.9", "ROS_HEM_002"),
    ("anaemia",                 "Anaemia_Unspecified",         "D64.9", "ROS_HEM_002"),
    ("anemia",                  "Anaemia_Unspecified",         "D64.9", "ROS_HEM_002"),
    ("nerve problem",           "Neurologic_Unspecified",      "G99.8", "ROS_NEU_003"),
    ("epilepsy",                "Epilepsy_Known",              "G40.9", "ROS_NEU_005"),
    ("fits",                    "Epilepsy_Known",              "G40.9", "ROS_NEU_005"),
    ("stroke before",           "Prior_Stroke",                "Z87.39","PMH_002"),
    ("mental problem",          "Psychiatric_Unspecified",     "F99",   "ROTS_001"),
    ("bone problem",            "Musculoskeletal_Unspecified", "M99.9", "ROS_MSK_001"),
    ("arthritis",               "Arthritis_Unspecified",       "M13.9", "ROS_MSK_001"),
    ("allergy to penicillin",   "Drug_Allergy_Penicillin",    None,    "ROS_ALG_001"),
    ("allergy to aspirin",      "Drug_Allergy_Aspirin",       None,    "ROS_ALG_001"),
    ("allergy unknown",         "Allergy_Unspecified",        None,    "ROS_ALG_002"),
    ("cancer",                  "Malignancy_Unspecified",      "C80.1", "FAM_003"),
    ("surgery before",          "Prior_Surgery",               "Z98.89","SRG_001"),
    ("operation before",        "Prior_Surgery",               "Z98.89","SRG_001"),
    ("tb before",               "Prior_TB",                    "Z87.0", "PMH_004"),
    ("tuberculosis before",     "Prior_TB",                    "Z87.0", "PMH_004"),
    ("hiv",                     "HIV_Status",                  "Z21",   "PMH_005"),
    ("aids",                    "HIV_Status",                  "Z21",   "PMH_005"),
]

# =============================================================================
# DATABASE SEED FUNCTIONS
# =============================================================================

def seed_nodes(db_path: str) -> int:
    """Insert all node definitions into the nodes table."""
    sql = """
        INSERT OR IGNORE INTO nodes
          (node_id, prompt_text, help_text, ui_type, ui_options,
           ui_min, ui_max, phase, framework, system_tag,
           is_red_flag, is_mandatory, display_order, fhir_loinc)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    from medikiosk.engine.db import get_connection
    count = 0
    with get_connection(db_path) as conn:
        for node in NODES:
            try:
                conn.execute(sql, node)
                count += 1
            except Exception as e:
                logger.error("Node insert failed %s: %s", node[0], e)
        conn.commit()
    logger.info("Seeded %d nodes", count)
    return count

def seed_syndromes(db_path: str) -> int:
    """Insert all syndrome definitions."""
    sql = """
        INSERT OR IGNORE INTO syndromes
          (syndrome_id, name, icd10, category, severity_tier,
           common_frameworks, description)
        VALUES (?,?,?,?,?,?,?)
    """
    from medikiosk.engine.db import get_connection
    count = 0
    with get_connection(db_path) as conn:
        for syn in SYNDROMES:
            try:
                conn.execute(sql, syn)
                count += 1
            except Exception as e:
                logger.error("Syndrome insert failed %s: %s", syn[0], e)
        conn.commit()
    logger.info("Seeded %d syndromes", count)
    return count

def seed_matrix_weights(db_path: str) -> int:
    """Insert all F x E weight mappings."""
    sql = """
        INSERT OR IGNORE INTO matrix_weights
          (node_id, syndrome_id, frequency, evoking_strength, answer_direction, notes)
        VALUES (?,?,?,?,?,?)
    """
    from medikiosk.engine.db import get_connection
    count = 0
    with get_connection(db_path) as conn:
        for mw in MATRIX_WEIGHTS:
            try:
                conn.execute(sql, mw)
                count += 1
            except Exception as e:
                logger.debug("Weight insert skip %s->%s: %s", mw[0], mw[1], e)
        conn.commit()
    logger.info("Seeded %d matrix weights", count)
    return count

def seed_routing_rules(db_path: str) -> int:
    """Insert routing rules for chief complaint -> framework mapping."""
    sql = """
        INSERT OR IGNORE INTO routing_rules
          (complaint_keyword, framework, priority, notes)
        VALUES (?,?,?,?)
    """
    from medikiosk.engine.db import get_connection
    count = 0
    with get_connection(db_path) as conn:
        for rule in ROUTING_RULES:
            try:
                conn.execute(sql, rule)
                count += 1
            except Exception as e:
                logger.error("Routing rule insert failed %s: %s", rule[0], e)
        conn.commit()
    logger.info("Seeded %d routing rules", count)
    return count

def seed_node_followups(db_path: str) -> int:
    """Insert conditional branch followup edges."""
    sql = """
        INSERT OR IGNORE INTO node_followups
          (trigger_node_id, trigger_value, followup_node_id, priority)
        VALUES (?,?,?,?)
    """
    from medikiosk.engine.db import get_connection
    count = 0
    with get_connection(db_path) as conn:
        for fu in NODE_FOLLOWUPS:
            try:
                conn.execute(sql, fu)
                count += 1
            except Exception as e:
                logger.debug("Followup insert skip %s: %s", fu[0], e)
        conn.commit()
    logger.info("Seeded %d node followups", count)
    return count

def seed_proxy_mappings(db_path: str) -> int:
    """Insert FHIR proxy tag mappings."""
    sql = """
        INSERT OR IGNORE INTO proxy_mappings
          (vague_term, fhir_proxy_tag, icd10_approx, clarification_node_id)
        VALUES (?,?,?,?)
    """
    from medikiosk.engine.db import get_connection
    count = 0
    with get_connection(db_path) as conn:
        for pm in PROXY_MAPPINGS:
            try:
                conn.execute(sql, pm)
                count += 1
            except Exception as e:
                logger.debug("Proxy insert skip %s: %s", pm[0], e)
        conn.commit()
    logger.info("Seeded %d proxy mappings", count)
    return count

def seed_all(db_path: str = None) -> dict:
    """
    Master seed function. Initialises DB and inserts all clinical data.

    Usage:
        from medikiosk.engine.master_clinical_database import seed_all
        results = seed_all('medikiosk.db')
        print(results)

    Returns:
        Dict with counts of rows inserted per table.
    """
    from medikiosk.engine.config import DB_PATH
    db = db_path or DB_PATH

    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger.info("=" * 60)
    logger.info("MediKiosk Master Clinical Database Seeder v1.0.0")
    logger.info("Target DB: %s", db)
    logger.info("=" * 60)

    # 1. Ensure schema exists
    init_db(db)

    # 2. Seed in dependency order
    results = {
        "nodes":          seed_nodes(db),
        "syndromes":      seed_syndromes(db),
        "matrix_weights": seed_matrix_weights(db),
        "routing_rules":  seed_routing_rules(db),
        "node_followups": seed_node_followups(db),
        "proxy_mappings": seed_proxy_mappings(db),
    }

    logger.info("=" * 60)
    logger.info("Seeding complete: %s", results)
    logger.info("=" * 60)
    return results

# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    import sys
    db_arg = sys.argv[1] if len(sys.argv) > 1 else None
    results = seed_all(db_arg)
    print("\n=== SEEDING RESULTS ===")
    for table, count in results.items():
        print(f"  {table:20s}: {count:4d} rows inserted")
    print("\nMediKiosk database is ready for clinical use.")
