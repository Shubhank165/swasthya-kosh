import { IntakeData } from '../types';

export const KIOSK_DATA: IntakeData = {
  schema_version: "0.2",
  intake_id: "82d32c07-a0e1-4e58-99c7-44be79ebfc42",
  kiosk_id: "jetson-opd-1",
  hospital_id: "aiia-delhi",
  status: "complete",
  language: "en",
  reporter: "self",
  department_code: "kayachikitsa",
  patient_ref: {
    "type": "guest",
    "value": null
  },
  engine_version: "medikiosk-0.1.0",
  content_version: "q1.60514d787ced",
  source: "kiosk",
  turns: [
    {
      "turn_id": 2,
      "question_id": "registration.age",
      "transcript": "18",
      "bound_field": "age",
      "resolved": true,
      "asr_confidence": 0.96,
      "rms": 512
    },
    {
      "turn_id": 4,
      "question_id": "ask_complaint",
      "transcript": "I have severe abdominal pain since morning",
      "bound_field": "chief_complaint",
      "resolved": true,
      "asr_confidence": 0.93,
      "rms": 508
    },
    {
      "turn_id": 5,
      "question_id": "ask_vomiting",
      "transcript": "No.",
      "bound_field": "screen_vomiting",
      "resolved": true,
      "asr_confidence": 0.98,
      "rms": 490
    },
    {
      "turn_id": 6,
      "question_id": "ask_bleeding",
      "transcript": "No.",
      "bound_field": "bleeding",
      "resolved": true,
      "asr_confidence": 0.99,
      "rms": 520
    }
  ],
  fields: {
    "age": {
      "status": "answered",
      "value": {
        "kind": "duration",
        "magnitude": 18.0,
        "unit": "year"
      },
      "original_text": "18",
      "language": "en",
      "source_turn": 2
    },
    "ayurveda_ahara_shakti": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "moderate"
      },
      "language": "en"
    },
    "ayurveda_dosha_tendency": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "pitta"
      },
      "language": "en"
    },
    "ayurveda_satmya": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "mixed"
      },
      "language": "en"
    },
    "ayurveda_satva": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "irritable"
      },
      "language": "en"
    },
    "ayurveda_vyayama_shakti": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "moderate"
      },
      "language": "en"
    },
    "bleeding": {
      "status": "answered",
      "value": {
        "kind": "boolean",
        "value": false
      },
      "original_text": "No.",
      "language": "en",
      "source_turn": 6
    },
    "breathlessness": {
      "status": "unresolved",
      "language": "en"
    },
    "chief_complaint": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "abdominal pain"
      },
      "language": "en",
      "source_turn": 4
    },
    "duration": {
      "status": "answered",
      "value": {
        "kind": "boolean",
        "value": false
      },
      "language": "en"
    },
    "reporter": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "self"
      },
      "language": "en"
    },
    "screen_fever": {
      "status": "answered",
      "value": {
        "kind": "boolean",
        "value": false
      },
      "language": "en"
    },
    "screen_vomiting": {
      "status": "answered",
      "value": {
        "kind": "boolean",
        "value": false
      },
      "original_text": "No.",
      "language": "en",
      "source_turn": 5
    },
    "severity": {
      "status": "answered",
      "value": {
        "kind": "scale",
        "value": 3.0,
        "minimum": 0.0,
        "maximum": 10.0
      },
      "language": "en"
    }
  },
  red_flags: [],
  abhaDetails: {
    abhaNumber: "91-4921-8834-0192",
    abhaAddress: "rahul.verma@abdm",
    verified: true,
    name: "Rahul Verma",
    gender: "Male",
    dob: "2008-04-12",
    photoUrl: "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=150&auto=format&fit=crop&q=80",
    linkedHealthRecords: 3
  },
  cameraVitals: {
    heartRateBpm: 76,
    respiratoryRateBpm: 17,
    confidence: 0.94,
    sensorType: "Jetson Orin rPPG Optical Sensor",
    extractionDurationSec: 15,
    timestamp: "2026-09-18 10:14 AM",
    spo2Estimate: 98,
    hrvMs: 64,
    qualityIndex: "Good"
  }
};

export const APP_DATA: IntakeData = {
  schema_version: "0.2",
  intake_id: "72a5a663-9b02-5e0c-aab4-647bfa9c964d",
  kiosk_id: null,
  hospital_id: "aiia-delhi",
  status: "complete",
  language: "hi",
  reporter: "self",
  department_code: "kayachikitsa",
  source: "app",
  app_version: "1.0.0",
  patient_ref: {
    "type": "phone",
    "value": "e3e1aaebb5585f85d76876971066137c03c04676cdc11961e2ed3315cf7c0afd"
  },
  engine_version: null,
  content_version: "q1.b9cca1aab749",
  turns: [
    { "turn_id": 1, "question_id": "fixed.complaints", "transcript": null, "bound_field": "routing.complaints", "resolved": true },
    { "turn_id": 2, "question_id": "fixed.chief_complaint", "transcript": null, "bound_field": "routing.chief_complaint", "resolved": true },
    { "turn_id": 3, "question_id": "fixed.timeline", "transcript": null, "bound_field": "fixed.timeline", "resolved": true },
    { "turn_id": 4, "question_id": "general.duration", "transcript": null, "bound_field": "general.duration", "resolved": true },
    { "turn_id": 5, "question_id": "general.onset", "transcript": null, "bound_field": "general.onset", "resolved": true },
    { "turn_id": 6, "question_id": "general.progression", "transcript": null, "bound_field": "general.progression", "resolved": true },
    { "turn_id": 7, "question_id": "general.severity", "transcript": null, "bound_field": "general.severity", "resolved": true },
    { "turn_id": 8, "question_id": "general.aggravating", "transcript": null, "bound_field": "general.aggravating", "resolved": true },
    { "turn_id": 9, "question_id": "general.relieving", "transcript": null, "bound_field": "general.relieving", "resolved": false },
    { "turn_id": 10, "question_id": "general.treatment_tried", "transcript": null, "bound_field": "general.treatment_tried", "resolved": false },
    { "turn_id": 11, "question_id": "general.pattern", "transcript": null, "bound_field": "general.pattern", "resolved": true },
    { "turn_id": 12, "question_id": "general.previous_episodes", "transcript": null, "bound_field": "general.previous_episodes", "resolved": true },
    { "turn_id": 13, "question_id": "digestive.nausea_vomiting", "transcript": null, "bound_field": "digestive.nausea", "resolved": true },
    { "turn_id": 14, "question_id": "digestive.relation_to_food", "transcript": null, "bound_field": "digestive.relation_to_food", "resolved": true },
    { "turn_id": 15, "question_id": "digestive.acidity", "transcript": null, "bound_field": "digestive.acidity", "resolved": true },
    { "turn_id": 16, "question_id": "digestive.appetite_change", "transcript": null, "bound_field": "digestive.appetite_change", "resolved": true },
    { "turn_id": 17, "question_id": "history.age", "transcript": null, "bound_field": "general.age", "resolved": true },
    { "turn_id": 18, "question_id": "history.allergies", "transcript": null, "bound_field": "general.allergies", "resolved": true },
    { "turn_id": 19, "question_id": "history.current_medications", "transcript": null, "bound_field": "general.current_medications", "resolved": false },
    { "turn_id": 20, "question_id": "history.known_conditions", "transcript": null, "bound_field": "general.known_conditions", "resolved": true },
    { "turn_id": 21, "question_id": "history.sex", "transcript": null, "bound_field": "general.sex", "resolved": true },
    { "turn_id": 22, "question_id": "history.past_surgery", "transcript": null, "bound_field": "general.past_surgery", "resolved": false },
    { "turn_id": 23, "question_id": "history.tobacco", "transcript": null, "bound_field": "general.tobacco", "resolved": true },
    { "turn_id": 24, "question_id": "history.alcohol", "transcript": null, "bound_field": "general.alcohol", "resolved": false },
    { "turn_id": 25, "question_id": "history.family_history", "transcript": null, "bound_field": "general.family_history", "resolved": true }
  ],
  fields: {
    "bleeding.amount": { "status": "not_applicable", "language": "hi" },
    "bleeding.ongoing": { "status": "not_applicable", "language": "hi" },
    "bleeding.site": { "status": "not_applicable", "language": "hi" },
    "bowel.blood_in_stool": { "status": "not_applicable", "language": "hi" },
    "bowel.consistency": { "status": "not_applicable", "language": "hi" },
    "bowel.incomplete_evacuation": { "status": "not_applicable", "language": "hi" },
    "bowel.stool_frequency": { "status": "not_applicable", "language": "hi" },
    "fatigue.effect_on_activity": { "status": "not_applicable", "language": "hi" },
    "fatigue.weight_change": { "status": "not_applicable", "language": "hi" },
    "fever.chills": { "status": "not_applicable", "language": "hi" },
    "fever.fever_pattern": { "status": "not_applicable", "language": "hi" },
    "fever.maximum_temperature": { "status": "not_applicable", "language": "hi" },
    "fever.measured": { "status": "not_applicable", "language": "hi" },
    "general.alcohol": { "status": "unresolved", "language": "hi", "source_turn": 24 },
    "general.current_medications": { "status": "unresolved", "language": "hi", "source_turn": 19 },
    "general.past_surgery": { "status": "unresolved", "language": "hi", "source_turn": 22 },
    "general.pregnancy": { "status": "not_applicable", "language": "hi" },
    "general.relieving": { "status": "unresolved", "language": "hi", "source_turn": 9 },
    "general.treatment_tried": { "status": "unresolved", "language": "hi", "source_turn": 10 },
    "headache.character": { "status": "not_applicable", "language": "hi" },
    "headache.light_sound_sensitivity": { "status": "not_applicable", "language": "hi" },
    "headache.site": { "status": "not_applicable", "language": "hi" },
    "headache.vision_change": { "status": "not_applicable", "language": "hi" },
    "joint.joints_affected": { "status": "not_applicable", "language": "hi" },
    "joint.movement_limited": { "status": "not_applicable", "language": "hi" },
    "joint.stiffness_timing": { "status": "not_applicable", "language": "hi" },
    "joint.swelling": { "status": "not_applicable", "language": "hi" },
    "menstrual.cycle_length": { "status": "not_applicable", "language": "hi" },
    "menstrual.cycle_regular": { "status": "not_applicable", "language": "hi" },
    "menstrual.flow": { "status": "not_applicable", "language": "hi" },
    "menstrual.last_period": { "status": "not_applicable", "language": "hi" },
    "menstrual.pain_with_periods": { "status": "not_applicable", "language": "hi" },
    "mental.appetite_or_sleep_affected": { "status": "not_applicable", "language": "hi" },
    "mental.effect_on_daily_life": { "status": "not_applicable", "language": "hi" },
    "mental.mood": { "status": "not_applicable", "language": "hi" },
    "other.description": { "status": "not_applicable", "language": "hi" },
    "pain.character": { "status": "not_applicable", "language": "hi" },
    "pain.radiation": { "status": "not_applicable", "language": "hi" },
    "pain.site": { "status": "not_applicable", "language": "hi" },
    "respiratory.breathlessness": { "status": "not_applicable", "language": "hi" },
    "respiratory.cough_type": { "status": "not_applicable", "language": "hi" },
    "respiratory.sputum_colour": { "status": "not_applicable", "language": "hi" },
    "respiratory.wheeze": { "status": "not_applicable", "language": "hi" },
    "skin.distribution": { "status": "not_applicable", "language": "hi" },
    "skin.itching": { "status": "not_applicable", "language": "hi" },
    "skin.lesion_type": { "status": "not_applicable", "language": "hi" },
    "skin.spreading": { "status": "not_applicable", "language": "hi" },
    "sleep.difficulty": { "status": "not_applicable", "language": "hi" },
    "sleep.hours": { "status": "not_applicable", "language": "hi" },
    "sleep.refreshed": { "status": "not_applicable", "language": "hi" },
    "urinary.blood_in_urine": { "status": "not_applicable", "language": "hi" },
    "urinary.burning": { "status": "not_applicable", "language": "hi" },
    "urinary.frequency_change": { "status": "not_applicable", "language": "hi" },
    "urinary.night_urination": { "status": "not_applicable", "language": "hi" },
    "urinary.urine_colour": { "status": "not_applicable", "language": "hi" },
    "general.allergies": {
      "status": "answered",
      "value": { "kind": "text", "text": "कुछ होता है" },
      "original_text": "कुछ कुछ होता है",
      "language": "hi",
      "source_turn": 18
    },
    "digestive.acidity": {
      "status": "answered",
      "value": { "kind": "boolean", "value": true },
      "original_text": "हाँ",
      "language": "hi",
      "source_turn": 15
    },
    "digestive.appetite_change": {
      "status": "answered",
      "value": { "kind": "text", "text": "reduced" },
      "original_text": "पहले से कम",
      "language": "hi",
      "source_turn": 16
    },
    "digestive.nausea": {
      "status": "answered",
      "value": { "kind": "text", "text": "nausea" },
      "original_text": "जी मिचलाना",
      "language": "hi",
      "source_turn": 13
    },
    "digestive.relation_to_food": {
      "status": "answered",
      "value": {
        "kind": "coded",
        "code": "worse_after_eating",
        "system": null,
        "display": null
      },
      "original_text": "खाने के बाद ज़्यादा",
      "language": "hi",
      "source_turn": 14
    },
    "fixed.timeline": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "दिक्कत तीन दिन पहले शुरू हुई और दिन ब दिन खराब होती गई"
      },
      "original_text": "दिक्कत तीन दिन पहले शुरू हुई और दिन ब दिन खराब होती गई",
      "language": "hi",
      "source_turn": 3
    },
    "general.age": {
      "status": "answered",
      "value": {
        "kind": "duration",
        "magnitude": 21.0,
        "unit": "year"
      },
      "original_text": "21 year",
      "language": "hi",
      "source_turn": 17
    },
    "general.aggravating": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "बाहर का खाना खाने से"
      },
      "original_text": "बाहर का खाना खाने से",
      "language": "hi",
      "source_turn": 8
    },
    "general.duration": {
      "status": "answered",
      "value": {
        "kind": "duration",
        "magnitude": 3.0,
        "unit": "day"
      },
      "original_text": "3 day",
      "language": "hi",
      "source_turn": 4
    },
    "general.family_history": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "asthma, thyroid"
      },
      "original_text": "दमा, थायरॉइड",
      "language": "hi",
      "source_turn": 25
    },
    "general.known_conditions": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "diabetes"
      },
      "original_text": "मधुमेह",
      "language": "hi",
      "source_turn": 20
    },
    "general.onset": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "gradual"
      },
      "original_text": "धीरे-धीरे",
      "language": "hi",
      "source_turn": 5
    },
    "general.pattern": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "constant"
      },
      "original_text": "हर समय",
      "language": "hi",
      "source_turn": 11
    },
    "general.previous_episodes": {
      "status": "answered",
      "value": {
        "kind": "boolean",
        "value": true
      },
      "original_text": "हाँ",
      "language": "hi",
      "source_turn": 12
    },
    "general.progression": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "worsening"
      },
      "original_text": "बिगड़ रहा है",
      "language": "hi",
      "source_turn": 6
    },
    "general.reporter": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "self"
      },
      "language": "hi"
    },
    "general.severity": {
      "status": "answered",
      "value": {
        "kind": "scale",
        "value": 7.0,
        "minimum": 0.0,
        "maximum": 10.0
      },
      "original_text": "7",
      "language": "hi",
      "source_turn": 7
    },
    "general.sex": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "male"
      },
      "original_text": "पुरुष",
      "language": "hi",
      "source_turn": 21
    },
    "general.tobacco": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "never"
      },
      "original_text": "कभी नहीं",
      "language": "hi",
      "source_turn": 23
    },
    "routing.chief_complaint": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "digestive"
      },
      "original_text": "पेट या पाचन की तकलीफ़",
      "language": "hi",
      "source_turn": 2
    },
    "routing.complaints": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "digestive"
      },
      "original_text": "पेट या पाचन की तकलीफ़",
      "language": "hi",
      "source_turn": 1
    },
    "condition_pain_in_lower_abdomen": {
      "status": "answered",
      "value": {
        "kind": "coded",
        "code": "pain_in_lower_abdomen",
        "system": null,
        "display": "Pain in lower abdomen"
      },
      "original_text": "पेन इन लोवर एब्डोमेन",
      "confidence": 0.9
    },
    "lab_hemoglobin": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "Hemoglobin: not read"
      },
      "original_text": "Hb",
      "confidence": 0.9
    },
    "lab_hiv": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "HIV: बी.वी.- ११०"
      },
      "original_text": "बी.वी.- ११०",
      "confidence": 0.75
    },
    "lab_hbsag": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "HBsAg: 60"
      },
      "original_text": "60",
      "confidence": 0.8
    },
    "lab_fbs/rbs": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "FBS/RBS: not read"
      },
      "original_text": "FBS/RBS",
      "confidence": 0.9
    },
    "lab_sugar": {
      "status": "answered",
      "value": {
        "kind": "quantity",
        "magnitude": 103.0,
        "unit": "M.K./J."
      },
      "original_text": "सुगर- १०३ एम की/जे.",
      "confidence": 0.7
    },
    "lab_widal_test": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "Widal Test: not read"
      },
      "original_text": "widal",
      "confidence": 0.9
    },
    "lab_malaria_parasite": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "Malaria Parasite: not read"
      },
      "original_text": "MP",
      "confidence": 0.9
    },
    "lab_sputum_for_afb/bs": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "Sputum For AFB/BS: not read"
      },
      "original_text": "Sputum For AFB/BS",
      "confidence": 0.9
    },
    "current_medications": {
      "status": "answered",
      "value": {
        "kind": "text",
        "text": "Dev Illo Flegan R"
      },
      "original_text": "देव इल्लो फ्लेगन र गोली",
      "confidence": 0.75
    }
  },
  red_flags: [],
  abhaDetails: {
    abhaNumber: "14-8832-9014-6631",
    abhaAddress: "amit.sharma@abdm",
    verified: true,
    name: "Amit Sharma",
    gender: "Male",
    dob: "2005-08-19",
    photoUrl: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80",
    linkedHealthRecords: 5
  },
  cameraVitals: {
    heartRateBpm: 84,
    respiratoryRateBpm: 20,
    confidence: 0.91,
    sensorType: "Kiosk Contactless Jetson-Camera (Optical rPPG)",
    extractionDurationSec: 20,
    timestamp: "2026-09-18 10:28 AM",
    spo2Estimate: 97,
    hrvMs: 52,
    qualityIndex: "Good"
  }
};

// Patient 3: Sunita Devi (Joint Stiffness / Sandhivata)
export const PATIENT_SUNITA_DATA: IntakeData = {
  schema_version: "0.2",
  intake_id: "c18a992e-5f12-4e92-80ea-31fa40a92021",
  kiosk_id: "jetson-opd-2",
  hospital_id: "aiia-delhi",
  status: "complete",
  language: "hi",
  reporter: "self",
  department_code: "kayachikitsa",
  source: "kiosk",
  patient_ref: { type: "guest", value: null },
  engine_version: "medikiosk-0.1.0",
  content_version: "q1.60514d787ced",
  turns: [
    { turn_id: 1, question_id: "registration.age", transcript: "46", bound_field: "age", resolved: true, asr_confidence: 0.97, rms: 504 },
    { turn_id: 2, question_id: "ask_complaint", transcript: "दोनों घुटनों में तेज दर्द और सुबह अकड़न रहती है", bound_field: "chief_complaint", resolved: true, asr_confidence: 0.94, rms: 520 },
    { turn_id: 3, question_id: "ask_duration", transcript: "छह महीने से", bound_field: "duration", resolved: true, asr_confidence: 0.95, rms: 510 },
    { turn_id: 4, question_id: "ask_swelling", transcript: "हाँ सूजन आती है", bound_field: "joint.swelling", resolved: true, asr_confidence: 0.92, rms: 495 }
  ],
  fields: {
    "age": { status: "answered", value: { kind: "duration", magnitude: 46.0, unit: "year" }, original_text: "46", language: "hi", source_turn: 1 },
    "chief_complaint": { status: "answered", value: { kind: "text", text: "Bilateral knee joint pain & morning stiffness (Sandhivata)" }, original_text: "दोनों घुटनों में तेज दर्द और सुबह अकड़न रहती है", language: "hi", source_turn: 2 },
    "duration": { status: "answered", value: { kind: "duration", magnitude: 6.0, unit: "month" }, original_text: "6 months", language: "hi", source_turn: 3 },
    "joint.swelling": { status: "answered", value: { kind: "boolean", value: true }, original_text: "हाँ सूजन आती है", language: "hi", source_turn: 4 },
    "severity": { status: "answered", value: { kind: "scale", value: 6.0, minimum: 0.0, maximum: 10.0 }, language: "hi" },
    "general.severity": { status: "answered", value: { kind: "scale", value: 6.0, minimum: 0.0, maximum: 10.0 }, language: "hi" },
    "ayurveda_dosha_tendency": { status: "answered", value: { kind: "text", text: "vata-kapha" }, language: "hi" },
    "ayurveda_ahara_shakti": { status: "answered", value: { kind: "text", text: "mandagni (low)" }, language: "hi" },
    "ayurveda_vyayama_shakti": { status: "answered", value: { kind: "text", text: "poor (restricted mobility)" }, language: "hi" },
    "ayurveda_satmya": { status: "answered", value: { kind: "text", text: "vata-aggravating cold dry foods" }, language: "hi" },
    "ayurveda_satva": { status: "answered", value: { kind: "text", text: "anxious" }, language: "hi" },
    "general.onset": { status: "answered", value: { kind: "text", text: "insidious / gradual" }, language: "hi" },
    "general.progression": { status: "answered", value: { kind: "text", text: "worsening with cold weather" }, language: "hi" },
    "general.aggravating": { status: "answered", value: { kind: "text", text: "ठंड में और सीढ़ियां चढ़ने पर" }, original_text: "ठंड में और सीढ़ियां चढ़ने पर", language: "hi" },
    "current_medications": { status: "answered", value: { kind: "text", text: "Yograj Guggulu & Pain spray" }, original_text: "योगराज गुग्गुलु व दर्द का स्प्रे", confidence: 0.82 },
    "lab_sugar": { status: "answered", value: { kind: "quantity", magnitude: 118.0, unit: "mg/dL" }, original_text: "शुगर ११८", confidence: 0.85 }
  },
  red_flags: [],
  abhaDetails: {
    abhaNumber: "22-5104-9912-3401",
    abhaAddress: "sunita.devi@abdm",
    verified: true,
    name: "Sunita Devi",
    gender: "Female",
    dob: "1980-02-14",
    linkedHealthRecords: 4
  },
  cameraVitals: {
    heartRateBpm: 72,
    respiratoryRateBpm: 16,
    confidence: 0.95,
    sensorType: "Jetson Orin rPPG Optical Sensor",
    extractionDurationSec: 15,
    timestamp: "2026-09-18 10:35 AM",
    spo2Estimate: 99,
    hrvMs: 68,
    qualityIndex: "Good"
  }
};

// Patient 4: Priya Patel (Migraine & Hyperacidity)
export const PATIENT_PRIYA_DATA: IntakeData = {
  schema_version: "0.2",
  intake_id: "f9024a1b-7822-4c22-b512-881902bb1139",
  kiosk_id: null,
  hospital_id: "aiia-delhi",
  status: "complete",
  language: "en",
  reporter: "self",
  department_code: "kayachikitsa",
  source: "app",
  app_version: "1.0.0",
  patient_ref: { type: "phone", value: "88a9ff0123bbaa778811" },
  engine_version: null,
  content_version: "q1.b9cca1aab749",
  turns: [
    { turn_id: 1, question_id: "fixed.complaints", transcript: null, bound_field: "routing.complaints", resolved: true },
    { turn_id: 2, question_id: "fixed.chief_complaint", transcript: null, bound_field: "routing.chief_complaint", resolved: true },
    { turn_id: 3, question_id: "headache.site", transcript: null, bound_field: "headache.site", resolved: true }
  ],
  fields: {
    "age": { status: "answered", value: { kind: "duration", magnitude: 29.0, unit: "year" }, original_text: "29", language: "en" },
    "chief_complaint": { status: "answered", value: { kind: "text", text: "Unilateral throbbing headache (Shirashoola) with severe acidity" }, language: "en" },
    "duration": { status: "answered", value: { kind: "duration", magnitude: 2.0, unit: "day" }, language: "en" },
    "severity": { status: "answered", value: { kind: "scale", value: 5.0, minimum: 0.0, maximum: 10.0 }, language: "en" },
    "general.severity": { status: "answered", value: { kind: "scale", value: 5.0, minimum: 0.0, maximum: 10.0 }, language: "en" },
    "ayurveda_dosha_tendency": { status: "answered", value: { kind: "text", text: "pitta-vata" }, language: "en" },
    "ayurveda_ahara_shakti": { status: "answered", value: { kind: "text", text: "tikshnagni (sharp)" }, language: "en" },
    "ayurveda_vyayama_shakti": { status: "answered", value: { kind: "text", text: "moderate" }, language: "en" },
    "ayurveda_satmya": { status: "answered", value: { kind: "text", text: "sensitive to skipped meals" }, language: "en" },
    "ayurveda_satva": { status: "answered", value: { kind: "text", text: "stressed" }, language: "en" },
    "general.onset": { status: "answered", value: { kind: "text", text: "acute episodic" }, language: "en" },
    "general.progression": { status: "answered", value: { kind: "text", text: "worsening with sunlight and screen time" }, language: "en" },
    "general.aggravating": { status: "answered", value: { kind: "text", text: "Fast food, skipping meals, sunlight" }, language: "en" },
    "current_medications": { status: "answered", value: { kind: "text", text: "Tab. Naproxen & Antacid" }, original_text: "Naproxen 250mg SOS", confidence: 0.88 },
    "lab_sugar": { status: "answered", value: { kind: "quantity", magnitude: 92.0, unit: "mg/dL" }, original_text: "RBS 92", confidence: 0.92 }
  },
  red_flags: [],
  abhaDetails: {
    abhaNumber: "73-1940-2051-7782",
    abhaAddress: "priya.patel@abdm",
    verified: true,
    name: "Priya Patel",
    gender: "Female",
    dob: "1997-11-09",
    linkedHealthRecords: 2
  },
  cameraVitals: {
    heartRateBpm: 80,
    respiratoryRateBpm: 18,
    confidence: 0.93,
    sensorType: "Kiosk Contactless Jetson-Camera (Optical rPPG)",
    extractionDurationSec: 15,
    timestamp: "2026-09-18 10:40 AM",
    spo2Estimate: 98,
    hrvMs: 55,
    qualityIndex: "Good"
  }
};

import { PatientQueueItem } from '../types';

export const OPD_PATIENT_QUEUE: PatientQueueItem[] = [
  {
    id: "p-042",
    tokenNumber: "#OPD-042",
    name: "Amit Sharma",
    age: 21,
    gender: "Male",
    source: "app",
    abhaNumber: "14-8832-9014-6631",
    abhaVerified: true,
    chiefComplaint: "Lower Abdominal Pain & Heartburn (Post outside food)",
    severity: 7,
    vitalsSummary: { hr: 84, rr: 20, spo2: 97 },
    queueStatus: "in_consultation",
    arrivalTime: "10:18 AM",
    intakeData: APP_DATA
  },
  {
    id: "p-041",
    tokenNumber: "#OPD-041",
    name: "Rahul Verma",
    age: 18,
    gender: "Male",
    source: "kiosk",
    kioskId: "jetson-opd-1",
    abhaNumber: "91-4921-8834-0192",
    abhaVerified: true,
    chiefComplaint: "Abdominal Pain & Epigastric Burning",
    severity: 3,
    vitalsSummary: { hr: 76, rr: 17, spo2: 98 },
    queueStatus: "waiting",
    arrivalTime: "10:12 AM",
    intakeData: KIOSK_DATA
  },
  {
    id: "p-043",
    tokenNumber: "#OPD-043",
    name: "Sunita Devi",
    age: 46,
    gender: "Female",
    source: "kiosk",
    kioskId: "jetson-opd-2",
    abhaNumber: "22-5104-9912-3401",
    abhaVerified: true,
    chiefComplaint: "Bilateral Knee Joint Pain & Morning Stiffness (Sandhivata)",
    severity: 6,
    vitalsSummary: { hr: 72, rr: 16, spo2: 99 },
    queueStatus: "waiting",
    arrivalTime: "10:25 AM",
    intakeData: PATIENT_SUNITA_DATA
  },
  {
    id: "p-044",
    tokenNumber: "#OPD-044",
    name: "Priya Patel",
    age: 29,
    gender: "Female",
    source: "app",
    abhaNumber: "73-1940-2051-7782",
    abhaVerified: true,
    chiefComplaint: "Unilateral Throbbing Headache (Shirashoola) & Acidity",
    severity: 5,
    vitalsSummary: { hr: 80, rr: 18, spo2: 98 },
    queueStatus: "waiting",
    arrivalTime: "10:32 AM",
    intakeData: PATIENT_PRIYA_DATA
  }
];

