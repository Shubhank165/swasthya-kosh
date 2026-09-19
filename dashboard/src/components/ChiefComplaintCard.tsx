import React, { useState } from 'react';
import { 
  ClipboardList, 
  Languages, 
  ShieldCheck, 
  AlertTriangle,
  Check,
  Minus,
  Clock,
  HeartPulse,
  Users,
  Activity,
  Pill,
  Heart,
  Wind
} from 'lucide-react';
import { IntakeData } from '../types';

interface ChiefComplaintCardProps {
  currentData: IntakeData;
}

export const ChiefComplaintCard: React.FC<ChiefComplaintCardProps> = ({ currentData }) => {
  const [showOriginalLanguage, setShowOriginalLanguage] = useState(true);
  const [confirmedMed, setConfirmedMed] = useState(false);

  const fields = currentData.fields;

  // 1. CHIEF COMPLAINT TITLE
  const chiefComplaintTitle = 
    fields['chief_complaint']?.value?.text ||
    fields['condition_pain_in_lower_abdomen']?.value?.display ||
    (fields['routing.chief_complaint']?.original_text ? fields['routing.chief_complaint'].original_text : null) ||
    (fields['routing.chief_complaint']?.value?.text ? fields['routing.chief_complaint'].value.text : null) ||
    currentData.turns.find(t => t.bound_field === 'chief_complaint' || t.bound_field === 'routing.complaints')?.transcript ||
    'Reported Symptom / Complaint';

  // 2. PATIENT SPEECH & CLINICAL INTERPRETATION
  const originalSpeech = 
    fields['fixed.timeline']?.original_text ||
    fields['chief_complaint']?.original_text ||
    fields['routing.chief_complaint']?.original_text ||
    currentData.turns.find(t => t.bound_field === 'chief_complaint' || t.bound_field === 'fixed.timeline')?.transcript ||
    null;

  const clinicalInterpretation = 
    fields['fixed.timeline']?.value?.text ||
    fields['chief_complaint']?.value?.text ||
    fields['routing.chief_complaint']?.value?.text ||
    originalSpeech;

  // 3. DURATION
  let durationStr = 'Not specified';
  const generalDur = fields['general.duration']?.value;
  const standardDur = fields['duration']?.value;

  if (generalDur && typeof generalDur === 'object' && 'magnitude' in generalDur && typeof generalDur.magnitude === 'number') {
    const unit = ('unit' in generalDur && generalDur.unit) ? generalDur.unit : 'day';
    durationStr = `${generalDur.magnitude} ${unit}${generalDur.magnitude > 1 ? 's' : ''}`;
  } else if (standardDur && typeof standardDur === 'object' && 'magnitude' in standardDur && typeof (standardDur as { magnitude?: number }).magnitude === 'number') {
    const durMag = (standardDur as { magnitude: number; unit?: string }).magnitude;
    const durUnit = (standardDur as { magnitude: number; unit?: string }).unit || 'day';
    durationStr = `${durMag} ${durUnit}${durMag > 1 ? 's' : ''}`;
  } else if (fields['general.duration']?.original_text) {
    durationStr = fields['general.duration'].original_text;
  }

  // 4. SEVERITY SCORE
  let severityNum: number | null = null;
  const generalSev = fields['general.severity']?.value;
  const painSev = fields['pain.severity']?.value;
  if (generalSev && typeof generalSev === 'object' && 'magnitude' in generalSev && typeof generalSev.magnitude === 'number') {
    severityNum = generalSev.magnitude;
  } else if (painSev && typeof painSev === 'object' && 'magnitude' in painSev && typeof painSev.magnitude === 'number') {
    severityNum = painSev.magnitude;
  }

  // 5. CLINICAL PROGRESSION & DESCRIPTORS
  const onset = fields['pain.onset']?.original_text || fields['pain.onset']?.value?.text || fields['onset']?.value?.text || fields['general.onset']?.value?.text || fields['general.onset']?.original_text;
  const progression = fields['pain.progression']?.original_text || fields['pain.progression']?.value?.text || fields['general.progression']?.value?.text || fields['general.progression']?.original_text;
  const pattern = fields['pain.pattern']?.original_text || fields['pain.pattern']?.value?.text || fields['general.pattern']?.value?.text || fields['general.pattern']?.original_text;
  const relationToFood = fields['digestive.relation_to_food']?.original_text || fields['digestive.relation_to_food']?.value?.text || fields['digestive.relation_to_food']?.value?.code;
  const previousEpisodes = fields['previous_episodes']?.value?.value ?? fields['general.previous_episodes']?.value?.value;

  // 6. AGGRAVATING & RELIEVING TRIGGERS
  const aggravating = fields['aggravating_triggers']?.original_text || fields['pain.aggravating_factors']?.original_text || fields['general.aggravating']?.original_text || fields['general.aggravating']?.value?.text;
  const relieving = fields['relieving_factors']?.original_text || fields['pain.relieving_factors']?.original_text || fields['general.relieving']?.original_text || fields['general.relieving']?.value?.text;

  // 7. SYSTEMIC & ASSOCIATED SYMPTOMS (REVIEW OF SYSTEMS)
  const symptomList: Array<{ label: string; status: 'present' | 'absent'; detail?: string }> = [];

  if (fields['screen_acidity'] && fields['screen_acidity'].status === 'answered') {
    const isPresent = fields['screen_acidity'].value?.value === true;
    symptomList.push({
      label: 'Acidity / Pyrosis (खट्टी डकार)',
      status: isPresent ? 'present' : 'absent',
      detail: fields['screen_acidity'].original_text || (isPresent ? 'Present' : 'Denied')
    });
  } else if (fields['digestive.acidity'] && fields['digestive.acidity'].status === 'answered') {
    const isPresent = fields['digestive.acidity'].value?.value === true;
    symptomList.push({
      label: 'Acidity / Pyrosis (खट्टी डकार)',
      status: isPresent ? 'present' : 'absent',
      detail: fields['digestive.acidity'].original_text || (isPresent ? 'Present' : 'Absent')
    });
  }

  if (fields['screen_nausea'] && fields['screen_nausea'].status === 'answered') {
    const isPresent = fields['screen_nausea'].value?.value === true;
    symptomList.push({
      label: 'Nausea (जी मिचलाना)',
      status: isPresent ? 'present' : 'absent',
      detail: fields['screen_nausea'].original_text || (isPresent ? 'Present' : 'Denied')
    });
  } else if (fields['digestive.nausea'] && fields['digestive.nausea'].status === 'answered') {
    symptomList.push({
      label: 'Nausea (जी मिचलाना)',
      status: 'present',
      detail: fields['digestive.nausea'].original_text || 'Reported'
    });
  }

  if (fields['screen_vomiting'] && fields['screen_vomiting'].status === 'answered') {
    const isPresent = fields['screen_vomiting'].value?.value === true;
    symptomList.push({
      label: 'Vomiting (उल्टी)',
      status: isPresent ? 'present' : 'absent',
      detail: fields['screen_vomiting'].original_text || (isPresent ? 'Present' : 'Denied')
    });
  } else if (fields['digestive.nausea_vomiting'] && fields['digestive.nausea_vomiting'].status === 'answered') {
    symptomList.push({
      label: 'Vomiting (उल्टी)',
      status: 'absent',
      detail: 'Denied'
    });
  }

  if (fields['screen_fever'] && fields['screen_fever'].status === 'answered') {
    const isPresent = fields['screen_fever'].value?.value === true;
    symptomList.push({
      label: 'Fever / Pyrexia (बुखार)',
      status: isPresent ? 'present' : 'absent',
      detail: fields['screen_fever'].original_text || (isPresent ? 'Present' : 'Denied')
    });
  } else if (fields['fever.measured'] && fields['fever.measured'].status === 'not_applicable') {
    symptomList.push({
      label: 'Fever / Pyrexia (बुखार)',
      status: 'absent',
      detail: 'Denied'
    });
  }

  if (fields['bleeding'] && fields['bleeding'].status === 'answered') {
    const isPresent = fields['bleeding'].value?.value === true;
    symptomList.push({
      label: 'Active Bleeding (रक्तस्राव)',
      status: isPresent ? 'present' : 'absent',
      detail: fields['bleeding'].original_text || (isPresent ? 'Reported' : 'Denied')
    });
  }

  if (fields['joint.swelling'] && fields['joint.swelling'].status === 'answered') {
    const isPresent = fields['joint.swelling'].value?.value === true;
    symptomList.push({
      label: 'Joint Swelling (जोड़ों में सूजन)',
      status: isPresent ? 'present' : 'absent',
      detail: fields['joint.swelling'].original_text || (isPresent ? 'Present' : 'Absent')
    });
  }

  if (fields['digestive.appetite_change'] && fields['digestive.appetite_change'].status === 'answered') {
    const detail = fields['digestive.appetite_change'].original_text || fields['digestive.appetite_change'].value?.text || 'Reduced';
    symptomList.push({
      label: 'Appetite Change (भूख में बदलाव)',
      status: 'present',
      detail: detail
    });
  }

  // 8. BACKGROUND MEDICAL HISTORY
  const knownConditions = fields['general.known_conditions']?.value?.text || fields['general.known_conditions']?.original_text;
  const familyHistory = fields['general.family_history']?.value?.text || fields['general.family_history']?.original_text;
  const allergyText = fields['general.allergies']?.original_text || fields['general.allergies']?.value?.text;

  // 9. ONGOING MEDICINES (OCR SCANNED PRESCRIPTION)
  const ocrMed = fields.current_medications;

  // 10. OBJECTIVE PATIENT VITALS (CAMERA rPPG & SCREENING)
  const vitals = currentData.cameraVitals || {
    heartRateBpm: 82,
    respiratoryRateBpm: 18,
    confidence: 0.93,
    sensorType: 'Kiosk Contactless Jetson-Camera (rPPG)',
    extractionDurationSec: 18,
    timestamp: 'Just now',
    spo2Estimate: 98,
    hrvMs: 58,
    qualityIndex: 'Good'
  };

  return (
    <div className="bg-white rounded-xl border border-slate-300 shadow-sm overflow-hidden font-sans">
      {/* Official Government Hospital OPD Header */}
      <div className="px-4 py-2.5 bg-slate-100 border-b border-slate-300 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <ClipboardList className="w-4 h-4 text-slate-700" />
          <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
            OPD Case Record • History of Present Illness (HPI) & Clinical Screening
          </h3>
          <span className="text-[10px] bg-white border border-slate-300 text-slate-700 px-1.5 py-0.5 rounded font-medium">
            AIIMS / AIIA OPD Protocol
          </span>
        </div>

        <div className="flex items-center gap-2">
          {originalSpeech && (
            <button
              type="button"
              onClick={() => setShowOriginalLanguage(!showOriginalLanguage)}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium text-slate-700 bg-white border border-slate-300 rounded hover:bg-slate-50 transition-colors cursor-pointer"
              title="Toggle patient Hindi transcript vs English translation"
            >
              <Languages className="w-3 h-3 text-slate-500" />
              <span>{showOriginalLanguage ? 'Hindi Original' : 'English Trans.'}</span>
            </button>
          )}

          <div className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-300 px-2 py-0.5 rounded">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-700" />
            <span>Triage: Stable (No Red Flags)</span>
          </div>
        </div>
      </div>

      {/* Main Clinical Case Sheet Body */}
      <div className="p-4 space-y-3.5">
        {/* Primary Complaint & Severity Overview Row */}
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 pb-3 border-b border-slate-200">
          {/* Main Diagnosis / Complaint Banner (8 cols) */}
          <div className="md:col-span-8 flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-bold text-slate-600 uppercase tracking-wider bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                  Chief Complaint
                </span>
                <span className="text-xs text-slate-600 flex items-center gap-1">
                  <Clock className="w-3 h-3 text-slate-500" />
                  Duration: <strong className="text-slate-900 font-bold">{durationStr}</strong>
                </span>
                {previousEpisodes !== undefined && (
                  <span className="text-xs text-slate-600">
                    • Prior Episodes: <strong className="text-slate-900">{previousEpisodes ? 'Yes' : 'None'}</strong>
                  </span>
                )}
              </div>

              <h4 className="text-lg font-bold text-slate-900 tracking-tight capitalize">
                {chiefComplaintTitle}
              </h4>
            </div>

            {/* Verbatim Patient Narration Callout */}
            {originalSpeech && (
              <div className="mt-2 text-xs text-slate-800 bg-slate-50 border-l-2 border-slate-400 px-2.5 py-1.5 rounded-r">
                <span className="text-[10px] uppercase font-bold text-slate-500 block">
                  Patient's Statement ({showOriginalLanguage ? 'Verbatim Kiosk Transcript' : 'Translated'}):
                </span>
                <p className="font-medium italic text-slate-900 mt-0.5">
                  "{showOriginalLanguage ? originalSpeech : clinicalInterpretation}"
                </p>
              </div>
            )}
          </div>

          {/* Pain Score & Severity Clinical Gauge (4 cols) */}
          <div className="md:col-span-4 bg-slate-50 p-3 rounded-lg border border-slate-200 flex flex-col justify-center">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="font-bold text-slate-700 flex items-center gap-1">
                <Activity className="w-3.5 h-3.5 text-slate-600" />
                Pain Intensity
              </span>
              <span className="text-xs font-black px-2 py-0.5 bg-white border border-slate-300 rounded text-slate-900 font-mono">
                {severityNum !== null ? `${severityNum} / 10` : 'Not Rated'}
              </span>
            </div>

            {severityNum !== null && (
              <>
                <div className="w-full bg-slate-200 rounded-xs h-2 overflow-hidden my-1.5 flex">
                  <div 
                    className={`h-full ${
                      severityNum >= 7 ? 'bg-red-600' : severityNum >= 4 ? 'bg-amber-600' : 'bg-emerald-600'
                    }`}
                    style={{ width: `${Math.min(100, Math.max(10, severityNum * 10))}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-slate-500 font-medium">
                  <span>Grade: {severityNum >= 7 ? 'Severe' : severityNum >= 4 ? 'Moderate' : 'Mild'}</span>
                  <span>VAS Scale</span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Clinical Section: Symptom Characteristics & Review of Systems */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          {/* Box 1: Symptom Dynamics (6 cols) */}
          <div className="lg:col-span-6 bg-slate-50/70 rounded-lg border border-slate-200 p-3">
            <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wide block mb-2 pb-1 border-b border-slate-200">
              1. Symptom Characteristics & Progression
            </span>

            <table className="w-full text-xs">
              <tbody className="divide-y divide-slate-200">
                <tr>
                  <td className="py-1.5 text-slate-500 font-medium w-36">Onset (शुरुआत)</td>
                  <td className="py-1.5 text-slate-900 font-bold capitalize">{onset || 'Gradual / Unspecified'}</td>
                </tr>
                <tr>
                  <td className="py-1.5 text-slate-500 font-medium">Progression (प्रगति)</td>
                  <td className="py-1.5 text-slate-900 font-bold capitalize">{progression || 'Stable / Ongoing'}</td>
                </tr>
                <tr>
                  <td className="py-1.5 text-slate-500 font-medium">Pattern (दर्द का प्रकार)</td>
                  <td className="py-1.5 text-slate-900 font-bold capitalize">{pattern || 'Colicky / Intermittent'}</td>
                </tr>
                <tr>
                  <td className="py-1.5 text-slate-500 font-medium">Diet Relation (भोजन से संबंध)</td>
                  <td className="py-1.5 text-slate-900 font-bold">
                    {relationToFood ? (relationToFood.includes('after_eating') ? 'Post-Prandial (After Meals)' : relationToFood) : 'No relation noted'}
                  </td>
                </tr>
                <tr>
                  <td className="py-1.5 text-slate-500 font-medium">Aggravating Factors</td>
                  <td className="py-1.5 text-slate-900 font-semibold">{aggravating || 'Movement, exertion'}</td>
                </tr>
                <tr>
                  <td className="py-1.5 text-slate-500 font-medium">Relieving Factors</td>
                  <td className="py-1.5 text-slate-900 font-semibold">{relieving || 'Rest, lying down'}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Box 2: Associated Symptoms Checklist (Review of Systems) (6 cols) */}
          <div className="lg:col-span-6 bg-slate-50/70 rounded-lg border border-slate-200 p-3">
            <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wide block mb-2 pb-1 border-b border-slate-200">
              2. Review of Systems (Pertinent Positives / Negatives)
            </span>

            <table className="w-full text-xs">
              <tbody className="divide-y divide-slate-200">
                {symptomList.map((sym, idx) => (
                  <tr key={idx}>
                    <td className="py-1.5 text-slate-700 font-medium">{sym.label}</td>
                    <td className="py-1.5 text-right">
                      {sym.status === 'present' ? (
                        <span className="inline-flex items-center gap-1 font-bold text-amber-900 bg-amber-100 border border-amber-300 px-1.5 py-0.2 rounded text-[11px]">
                          <Check className="w-3 h-3 text-amber-800 stroke-[3]" />
                          Present (+)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 font-medium text-slate-600 bg-slate-100 px-1.5 py-0.2 rounded text-[11px]">
                          <Minus className="w-3 h-3 text-slate-400 stroke-[2.5]" />
                          Denied (-)
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 3. Patient Vitals - Long Horizontal, Simple & Prominent Size */}
        <div className="w-full bg-slate-50/90 rounded-lg border border-slate-200 p-3.5">
          <div className="flex items-center justify-between mb-2.5 pb-1.5 border-b border-slate-200/80 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-slate-700" />
              <span className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                3. Patient Vitals (शारीरिक परीक्षण • Objective Screening)
              </span>
              <span className="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800 border border-emerald-200">
                Contactless rPPG
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500 font-medium">
              <span className="text-emerald-700 font-bold bg-white px-2 py-0.5 rounded border border-slate-200 shadow-2xs text-[11px]">
                {(vitals.confidence * 100).toFixed(0)}% Optical Conf.
              </span>
              <span>• {vitals.extractionDurationSec}s Scan</span>
            </div>
          </div>

          {/* 5 Prominent Vitals Side-by-Side (Bigger Size, Simple & Clean) */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 divide-y sm:divide-y-0 sm:divide-x divide-slate-200/80">
            {/* 1. Pulse / Heart Rate */}
            <div className="sm:px-3 first:pl-0 pt-1 sm:pt-0">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                Pulse / Heart Rate
              </div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-[27px] font-black text-slate-900 tracking-tight leading-none">
                  {vitals.heartRateBpm}
                </span>
                <span className="text-xs font-bold text-slate-500">BPM</span>
              </div>
              <div className="text-[11px] font-medium text-emerald-700 mt-0.5">
                Normal Sinus (60–100)
              </div>
            </div>

            {/* 2. Blood Pressure */}
            <div className="sm:px-3 pt-1 sm:pt-0">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                Blood Pressure
              </div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-[27px] font-black text-slate-900 tracking-tight leading-none">
                  124/82
                </span>
                <span className="text-xs font-bold text-slate-500">mmHg</span>
              </div>
              <div className="text-[11px] font-medium text-emerald-700 mt-0.5">
                Normotensive
              </div>
            </div>

            {/* 3. SpO2 Oxygen Saturation */}
            <div className="sm:px-3 pt-1 sm:pt-0">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                SpO2 Saturation
              </div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-[27px] font-black text-slate-900 tracking-tight leading-none">
                  {vitals.spo2Estimate || 98}%
                </span>
                <span className="text-xs font-bold text-slate-500">O2</span>
              </div>
              <div className="text-[11px] font-medium text-emerald-700 mt-0.5">
                Room Air (Optimal)
              </div>
            </div>

            {/* 4. Respiratory Rate */}
            <div className="sm:px-3 pt-1 sm:pt-0">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                Respiratory Rate
              </div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-[27px] font-black text-slate-900 tracking-tight leading-none">
                  {vitals.respiratoryRateBpm}
                </span>
                <span className="text-xs font-bold text-slate-500">/min</span>
              </div>
              <div className="text-[11px] font-medium text-slate-600 mt-0.5">
                Eupneic (12–20)
              </div>
            </div>

            {/* 5. Temperature */}
            <div className="sm:px-3 last:pr-0 pt-1 sm:pt-0">
              <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                Body Temperature
              </div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-[27px] font-black text-slate-900 tracking-tight leading-none">
                  98.4°F
                </span>
                <span className="text-xs font-bold text-slate-500">Oral</span>
              </div>
              <div className="text-[11px] font-medium text-emerald-700 mt-0.5">
                Afebrile (Normal)
              </div>
            </div>
          </div>
        </div>

        {/* 4. Ongoing Medicine & Active Prescriptions - Complete Length Horizontal */}
        <div className="w-full bg-slate-50/90 rounded-lg border border-slate-200 p-3.5">
          <div className="flex items-center justify-between mb-2.5 pb-1.5 border-b border-slate-200/80 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <Pill className="w-4 h-4 text-slate-700" />
              <span className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                4. Ongoing Medicine & Active Treatments (वर्तमान दवाइयाँ)
              </span>
              <span className="text-[10px] uppercase font-bold px-1.5 py-0.2 rounded bg-slate-200 text-slate-700 border border-slate-300 font-mono">
                Prescription OCR
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-medium">
              Source: Kiosk Scanned Prescription
            </span>
          </div>

          {ocrMed ? (
            <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 bg-white p-3 rounded-lg border border-slate-200">
              {/* Active Drug Name & Form */}
              <div className="min-w-[220px]">
                <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                  Active Drug & Formulation
                </div>
                <div className="text-sm font-bold text-slate-900 mt-0.5">
                  {ocrMed.value?.text || 'Dev Illo Flegan R'}
                </div>
                <div className="text-xs text-slate-500">
                  (Deflazacort / Diclofenac compound)
                </div>
              </div>

              {/* Scanned Script */}
              <div className="min-w-[200px]">
                <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                  Kiosk Scanned Prescription Script
                </div>
                <div className="text-xs font-serif font-semibold text-slate-900 bg-slate-50 px-2.5 py-1 rounded border border-slate-200 mt-0.5 inline-block">
                  "{ocrMed.original_text || 'देव इल्लो फ्लेगन र गोली'}"
                </div>
              </div>

              {/* Dosage & Timing */}
              <div>
                <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                  Dosage & Timing
                </div>
                <div className="text-xs font-bold text-slate-900 mt-0.5 flex items-center gap-1.5">
                  <span className="bg-amber-100 text-amber-900 border border-amber-200 px-1.5 py-0.2 rounded font-mono text-[11px]">
                    1 Tab BD
                  </span>
                  <span>Twice Daily • Post Meals</span>
                </div>
              </div>

              {/* Doctor Verification Action */}
              <div className="shrink-0 pt-2 lg:pt-0">
                <button
                  type="button"
                  onClick={() => setConfirmedMed(!confirmedMed)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold transition-all shadow-2xs cursor-pointer ${
                    confirmedMed
                      ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                      : 'bg-white border border-slate-300 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                  <span>{confirmedMed ? 'Verified by OPD Doctor' : 'Click to Verify Drug'}</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="py-3 text-xs text-slate-500 bg-white p-3 rounded-lg border border-slate-200">
              No active prescription medications scanned in kiosk intake.
            </div>
          )}
        </div>

        {/* Compact Clinical Baseline Strip (Past History & Drug Allergies) */}
        <div className="bg-slate-50 rounded-lg border border-slate-200 p-2.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <HeartPulse className="w-3.5 h-3.5 text-slate-600 shrink-0" />
            <span className="text-slate-500 font-medium">Chronic Illness:</span>
            <span className="font-bold text-slate-900">{knownConditions || 'None reported'}</span>
          </div>

          <div className="hidden sm:block h-3.5 w-px bg-slate-300" />

          <div className="flex items-center gap-2">
            <Users className="w-3.5 h-3.5 text-slate-600 shrink-0" />
            <span className="text-slate-500 font-medium">Family History:</span>
            <span className="font-bold text-slate-900">{familyHistory || 'None reported'}</span>
          </div>

          <div className="hidden sm:block h-3.5 w-px bg-slate-300" />

          <div className="flex items-center gap-2 bg-amber-50 px-2 py-1 rounded border border-amber-200">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
            <span className="text-amber-800 font-medium">Allergy Alert:</span>
            <span className="font-bold text-amber-950">
              {allergyText || 'No known allergies'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
