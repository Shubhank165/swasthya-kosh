import React, { useState } from 'react';
import { 
  Leaf, 
  Flame, 
  Apple, 
  Brain, 
  HeartPulse, 
  Check, 
  AlertCircle
} from 'lucide-react';
import { IntakeData } from '../types';

interface AyurvedicProfileProps {
  currentData: IntakeData;
}

export const AyurvedicProfile: React.FC<AyurvedicProfileProps> = ({ currentData }) => {
  const [activeSubTab, setActiveSubTab] = useState<'prakriti' | 'pariksha' | 'chikitsa'>('prakriti');
  const fields = currentData.fields;

  /**
   * Dashavidha Pariksha, as the kiosk reported it.
   *
   * These used to default to 'pitta' / 'moderate' / 'mixed' when the fact was
   * absent, which put a constitutional finding on the screen for a patient
   * nobody had assessed. A Prakriti is a clinical act performed by a Vaidya;
   * inventing one is the worst version of the fabricated-vitals problem, not a
   * milder one. Absent now reads as absent.
   */
  const dosha = fields.ayurveda_dosha_tendency?.value?.text ?? null;
  const aharaShakti = fields.ayurveda_ahara_shakti?.value?.text ?? null;
  const vyayamaShakti = fields.ayurveda_vyayama_shakti?.value?.text ?? null;
  const satmya = fields.ayurveda_satmya?.value?.text ?? null;
  const satva = fields.ayurveda_satva?.value?.text ?? null;
  const prakritiSelfReport = fields.prakriti_self_report?.value?.text ?? null;

  /**
   * The phone app's AYUSH module, which is a different instrument.
   *
   * The kiosk runs Dashavidha Pariksha and sends `ayurveda_*`; the app walks a
   * 62-item CCRAS Prakriti questionnaire and sends `ayush.*`. They are
   * deliberately **not** aliased onto each other — "Ahara Shakti" and "skin
   * texture" are not two names for one observation, and merging them would put
   * a classical parameter on a sheet that no question established. So each is
   * shown as itself, under its own heading, and a record carrying neither says
   * so.
   */
  const ayushItems = Object.entries(fields)
    .filter(([fieldId, item]) => fieldId.startsWith('ayush.') && item.status === 'answered')
    .map(([fieldId, item]) => ({
      fieldId,
      // The backend labels these; it is the only place allowed to name a
      // clinical field, and deriving a display string here would be the
      // dashboard inventing content.
      label: fieldId.slice('ayush.'.length).replace(/_/g, ' '),
      value: item.value?.text ?? item.value?.display ?? item.original_text ?? '',
    }))
    .filter((row) => row.value !== '');

  const hasDashavidha = Boolean(
    dosha || aharaShakti || vyayamaShakti || satmya || satva || prakritiSelfReport,
  );

  // Dynamic suspected roga & chikitsa derived directly from JSON fields
  const complaintText = (
    fields.chief_complaint?.value?.text || 
    fields.condition_pain_in_lower_abdomen?.value?.display || 
    fields['routing.chief_complaint']?.value?.text || 
    ''
  ).toLowerCase();

  /**
   * Whether the complaint matched any pattern below.
   *
   * The Roga, Samprapti, Chikitsa, Pathya/Apathya and three formulations that
   * follow are a hardcoded lookup on the complaint text, and Amlapitta was its
   * *default* — so a patient whose complaint was "mental" was shown a suspected
   * diagnosis of hyperacidity, a samprapti, and three named medicines with
   * doses. That is a prescription for a condition nobody suspected.
   *
   * The lookup is left as it is for the three patterns it genuinely recognises,
   * but it no longer falls through to one. An unmatched complaint says the
   * mapping does not cover it, and the block is not rendered at all.
   */
  let matchedRoga = false;
  let suspectedRoga = 'Amlapitta (Hyperacidity / Vidagdhajirna)';
  let samprapti = 'Pitta vitiation with Drava & Tikshna Guna increase';
  let chikitsaPrinciple = 'Deepana, Pachana, and Pitta-shamana followed by gentle Anulomana. Eradicate Aama dosha before prescribing heavy Rasayana formulations.';
  let pathyaItems = [
    'Mudga Yusha (warm green gram soup) & boiled barley water.',
    'Cooling natural remedies: Dhanyaka Jala (coriander seed infusion), Fresh Amla juice.',
    'Maintain regular meal timings; do not sleep immediately after dinner.'
  ];
  let apathyaItems = [
    'Deep-fried street foods, sour fermented batters, pickles, and hot chilies.',
    'Excessive tea, coffee, carbonated acidic beverages, and smoking.',
    'Late night heavy meals and suppression of natural urges (Vega-dharana).'
  ];
  let formulation1 = { name: 'Avipattikar Churna', dose: '3-5g twice daily with lukewarm water before meals.', role: 'Deepana & Pachana' };
  let formulation2 = { name: 'Kamadudha Rasa (Mukta-yukta)', dose: '250mg twice daily with lukewarm milk to cool acidity.', role: 'Pitta Shamana' };
  let formulation3 = { name: 'Triphala / Drakshasava', dose: '15-20ml with equal water post-dinner for mild laxative action.', role: 'Anulomana' };

  if (complaintText.includes('acid') || complaintText.includes('amlapitta') || complaintText.includes('heartburn')) {
    matchedRoga = true;
  } else if (complaintText.includes('knee') || complaintText.includes('joint') || complaintText.includes('sandhivata') || (dosha?.includes('vata-kapha') ?? false)) {
    matchedRoga = true;
    suspectedRoga = 'Sandhivata (Osteoarthritis / Vata-Kapha Joint Disorder)';
    samprapti = 'Vata aggravation causing Dhatukshaya (cartilage wear) & joint stiffness';
    chikitsaPrinciple = 'Vata-shamana, Snehana-Swedana, Agni Deepana, and Shothahara (anti-inflammatory) principles.';
    pathyaItems = [
      'Warm freshly cooked light meals with cow ghee (Ghrita) and sesame oil.',
      'Gentle joint mobilization and warm fomentation (Swedana).',
      'Warm ginger-turmeric water (Sunthi-Haridra Jala) to digest Aama.'
    ];
    apathyaItems = [
      'Cold, dry, stale, or refrigerated foods (Vata-aggravating ahara).',
      'Direct exposure to cold breeze or excessive stair climbing.',
      'Heavy gassy legumes (Chickpeas/Rajma) causing Vata distention.'
    ];
    formulation1 = { name: 'Yograj Guggulu', dose: '2 tablets twice daily with warm water after meals.', role: 'Shoola & Shothahara' };
    formulation2 = { name: 'Dashamoola Kwatha', dose: '20ml with equal warm water morning and evening.', role: 'Vata Shamana' };
    formulation3 = { name: 'Mahanarayana Taila', dose: 'External gentle application to affected joints twice daily.', role: 'Snehana & Vedanasthapana' };
  } else if (complaintText.includes('headache') || complaintText.includes('migraine') || complaintText.includes('shirashoola') || (dosha?.includes('pitta-vata') ?? false)) {
    matchedRoga = true;
    suspectedRoga = 'Ardhavabhedaka / Shirashoola (Vascular Cephalea / Pitta-Vata Shiroroga)';
    samprapti = 'Rakta-Pitta vitiation provoked by Ushna-Tikshna triggers and irregular eating';
    chikitsaPrinciple = 'Shiro-abhyanga, Pratimarsha Nasya, Pitta Shamana, and stress alleviation.';
    pathyaItems = [
      'Hydration, coconut water, sweet cooling fruits (pomegranate, sweet grapes).',
      'Timely meals to prevent hunger-induced migraine provocation.',
      'Quiet, dimly lit room rest during acute headache episodes.'
    ];
    apathyaItems = [
      'Skipping meals (Upavasa) and prolonged screen exposure under harsh lighting.',
      'Fermented, excessively salty, or preservative-laden processed foods.',
      'Direct intense sun exposure (Atapa Sevana) without head protection.'
    ];
    formulation1 = { name: 'Pathyadi Kwatha', dose: '15-20ml with equal water twice daily before meals.', role: 'Shiroroga Shamana' };
    formulation2 = { name: 'Shirashooladivajra Rasa', dose: '1 tablet twice daily with honey or warm milk.', role: 'Vedanasthapana' };
    formulation3 = { name: 'Anu Taila', dose: '2 drops in each nostril in morning (Pratimarsha Nasya).', role: 'Nasya Chikitsa' };
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs overflow-hidden">
      {/* Rich Saffron-to-Emerald Ayurvedic Header */}
      <div className="px-5 py-4 bg-gradient-to-r from-amber-900/5 via-amber-50/50 to-emerald-900/5 border-b border-slate-100 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-500 to-emerald-600 flex items-center justify-center text-white shadow-xs">
            <Leaf className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-slate-900">
                Ayurvedic Clinical Profile & Prakriti Assessment
              </h3>
              <span className="text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-300 px-2 py-0.5 rounded-full">
                AIIA Kayachikitsa
              </span>
            </div>
          </div>
        </div>

        {/* View mode switcher */}
        <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl text-xs">
          <button
            type="button"
            onClick={() => setActiveSubTab('prakriti')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
              activeSubTab === 'prakriti'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Prakriti & Agni
          </button>
          <button
            type="button"
            onClick={() => setActiveSubTab('pariksha')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
              activeSubTab === 'pariksha'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Ashtavidha Pariksha
          </button>
          <button
            type="button"
            onClick={() => setActiveSubTab('chikitsa')}
            className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
              activeSubTab === 'chikitsa'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Chikitsa Guidance
          </button>
        </div>
      </div>

      <div className="p-5 space-y-4">
        {/* Suspected Vyadhi. Shown only where the complaint mapping recognises
            the complaint — never as a default. */}
        {matchedRoga ? (
          <div className="p-3.5 bg-amber-50/60 border border-amber-200/80 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="text-[11px] font-bold text-amber-900 bg-amber-200/70 px-2 py-0.5 rounded-md uppercase tracking-wider">
                Suspected Roga
              </span>
              <span className="text-sm font-bold text-amber-950">{suspectedRoga}</span>
            </div>
            {dosha && (
              <span className="text-xs font-bold text-amber-900 bg-white/90 px-2.5 py-1 rounded-lg border border-amber-200 shadow-2xs self-start sm:self-auto">
                Dosha: <strong className="capitalize text-amber-950">{dosha}</strong>
              </span>
            )}
          </div>
        ) : (
          <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-600">
            No suspected Roga shown — this complaint is not covered by the
            dashboard's complaint mapping, and a default would be a guess at a
            diagnosis. The recorded complaint and findings are below.
          </div>
        )}

        {/* 1. Prakriti & Agni View */}
        {activeSubTab === 'prakriti' && (
          <div className="space-y-4">
            {!hasDashavidha && ayushItems.length === 0 && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-6 text-center">
                <p className="text-sm font-semibold text-slate-700">
                  No Ayurvedic assessment on this record
                </p>
                <p className="mt-1 text-xs text-slate-500 max-w-md mx-auto">
                  Neither the kiosk's Dashavidha Pariksha nor the app's Prakriti
                  questionnaire was completed for this visit.
                </p>
              </div>
            )}

            {ayushItems.length > 0 && (
              <div className="rounded-xl border border-violet-200/80 bg-violet-50/40 overflow-hidden">
                <div className="px-4 py-2.5 border-b border-violet-200/70 flex items-center justify-between gap-2 flex-wrap">
                  <h4 className="text-xs font-bold text-violet-950 uppercase tracking-wide">
                    Prakriti questionnaire (CCRAS, patient-reported)
                  </h4>
                  <span className="text-[10px] font-semibold bg-violet-100 text-violet-900 px-2 py-0.5 rounded-full border border-violet-200">
                    {ayushItems.length} of 62 answered · from the app
                  </span>
                </div>
                <dl className="divide-y divide-violet-100">
                  {ayushItems.map((row) => (
                    <div key={row.fieldId} className="px-4 py-2 flex items-baseline gap-3 text-xs">
                      <dt className="w-1/2 shrink-0 text-slate-600 capitalize">{row.label}</dt>
                      <dd className="font-semibold text-slate-900">{row.value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="px-4 py-2 text-[11px] text-violet-900/70 border-t border-violet-100">
                  A self-reported instrument, not a Vaidya's classification. Item
                  weights are provisional until reviewed.
                </p>
              </div>
            )}

            {hasDashavidha && (
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">
                Dashavidha Pariksha · from the kiosk
              </p>
            )}
            {/* 4 Colorful Vitality Markers (Orange, Emerald, Purple, Blue) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {/* Dosha Tendency */}
              <div className="bg-orange-50/60 rounded-xl p-3.5 border border-orange-200/80">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-orange-900 flex items-center gap-1.5">
                    <Flame className="w-4 h-4 text-orange-600" />
                    Dosha Tendency
                  </span>
                  <span className="text-[10px] uppercase font-bold bg-orange-100/90 text-orange-900 px-2 py-0.5 rounded">
                    Prakriti
                  </span>
                </div>
                <div className="text-lg font-bold text-orange-950 capitalize">
                  {dosha ? `${dosha} Pradhana` : 'Not assessed'}
                </div>
                <p className="text-xs text-orange-800/80 mt-1">
                  Evaluated through physical and functional symptom indicators in intake.
                </p>
              </div>

              {/* Ahara Shakti */}
              <div className="bg-emerald-50/60 rounded-xl p-3.5 border border-emerald-200/80">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-emerald-900 flex items-center gap-1.5">
                    <Apple className="w-4 h-4 text-emerald-600" />
                    Ahara Shakti
                  </span>
                  <span className="text-[10px] uppercase font-bold bg-emerald-100/90 text-emerald-900 px-2 py-0.5 rounded">
                    Agni Status
                  </span>
                </div>
                <div className="text-lg font-bold text-emerald-950 capitalize">
                  {aharaShakti ?? 'Not assessed'} Agni
                </div>
                <p className="text-xs text-emerald-800/80 mt-1">
                  Digestive power and metabolic fire status recorded during interview.
                </p>
              </div>

              {/* Satva Temperament */}
              <div className="bg-purple-50/60 rounded-xl p-3.5 border border-purple-200/80">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-purple-900 flex items-center gap-1.5">
                    <Brain className="w-4 h-4 text-purple-600" />
                    Satva (Resilience)
                  </span>
                  <span className="text-[10px] uppercase font-bold bg-purple-100/90 text-purple-900 px-2 py-0.5 rounded">
                    Mental Bala
                  </span>
                </div>
                <div className="text-lg font-bold text-purple-950 capitalize">
                  {satva ?? 'Not assessed'} Satva
                </div>
                <p className="text-xs text-purple-800/80 mt-1">
                  Emotional disposition and stress reaction profile.
                </p>
              </div>

              {/* Satmya & Vyayama */}
              <div className="bg-blue-50/60 rounded-xl p-3.5 border border-blue-200/80">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-blue-900 flex items-center gap-1.5">
                    <HeartPulse className="w-4 h-4 text-blue-600" />
                    Vyayama & Satmya
                  </span>
                  <span className="text-[10px] uppercase font-bold bg-blue-100/90 text-blue-900 px-2 py-0.5 rounded">
                    Physical Bala
                  </span>
                </div>
                <div className="text-xs font-semibold text-blue-950 mt-1">
                  Physical: <span className="capitalize text-blue-800">{vyayamaShakti ?? 'Not assessed'}</span>
                </div>
                <div className="text-xs font-semibold text-blue-950 mt-0.5">
                  Habituation: <span className="capitalize text-blue-800">{satmya ?? 'Not assessed'}</span>
                </div>
              </div>
            </div>

            {/* Pathya / Apathya. Same fixed complaint mapping as the Roga above,
                so it is shown on the same condition — diet and regimen advice
                for a condition nobody suspected is still advice. */}
            {matchedRoga && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 pt-1">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/30 p-3.5">
                <div className="text-xs font-bold text-emerald-900 flex items-center gap-1.5 mb-2">
                  <Check className="w-4 h-4 text-emerald-600" />
                  <span>Recommended Pathya (Beneficial Diet & Regimen)</span>
                </div>
                <ul className="text-xs text-slate-700 space-y-1.5 list-disc list-inside">
                  {pathyaItems.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>

              <div className="rounded-xl border border-rose-200 bg-rose-50/30 p-3.5">
                <div className="text-xs font-bold text-rose-900 flex items-center gap-1.5 mb-2">
                  <AlertCircle className="w-4 h-4 text-rose-600" />
                  <span>Strict Apathya (Contraindicated Foods & Habits)</span>
                </div>
                <ul className="text-xs text-slate-700 space-y-1.5 list-disc list-inside">
                  {apathyaItems.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
            )}
          </div>
        )}

        {/* 2. Ashtavidha Pariksha View with Distinctive Ayurvedic Colors */}
        {activeSubTab === 'pariksha' && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <div className="p-3 rounded-xl bg-amber-50/50 border border-amber-200/70">
                <span className="text-[10px] font-bold text-amber-800 uppercase">1. Nadi (Pulse)</span>
                <p className="text-xs font-bold text-slate-900 mt-1">Pitta-Vata Gati</p>
                <p className="text-[11px] text-slate-500">Rapid, steady rhythm</p>
              </div>

              <div className="p-3 rounded-xl bg-emerald-50/50 border border-emerald-200/70">
                <span className="text-[10px] font-bold text-emerald-800 uppercase">2. Jihva (Tongue)</span>
                <p className="text-xs font-bold text-slate-900 mt-1">Saama (Coated)</p>
                <p className="text-[11px] text-slate-500">Light white coating, Aama present</p>
              </div>

              <div className="p-3 rounded-xl bg-orange-50/50 border border-orange-200/70">
                <span className="text-[10px] font-bold text-orange-800 uppercase">3. Sparsha (Touch)</span>
                <p className="text-xs font-bold text-slate-900 mt-1">Ishat Ushna</p>
                <p className="text-[11px] text-slate-500">Normal to slightly warm</p>
              </div>

              <div className="p-3 rounded-xl bg-blue-50/50 border border-blue-200/70">
                <span className="text-[10px] font-bold text-blue-800 uppercase">4. Drik (Eyes)</span>
                <p className="text-xs font-bold text-slate-900 mt-1">Prakrita (Normal)</p>
                <p className="text-[11px] text-slate-500">No scleral icterus</p>
              </div>

              <div className="p-3 rounded-xl bg-purple-50/50 border border-purple-200/70">
                <span className="text-[10px] font-bold text-purple-800 uppercase">5. Shabda (Voice)</span>
                <p className="text-xs font-bold text-slate-900 mt-1">Spashta (Clear)</p>
                <p className="text-[11px] text-slate-500">Normal articulation</p>
              </div>

              <div className="p-3 rounded-xl bg-rose-50/50 border border-rose-200/70">
                <span className="text-[10px] font-bold text-rose-800 uppercase">6. Mala (Bowel)</span>
                <p className="text-xs font-bold text-slate-900 mt-1">Vibandha / Regular</p>
                <p className="text-[11px] text-slate-500">Habitual evacuation</p>
              </div>

              <div className="p-3 rounded-xl bg-sky-50/50 border border-sky-200/70">
                <span className="text-[10px] font-bold text-sky-800 uppercase">7. Mutra (Urine)</span>
                <p className="text-xs font-bold text-slate-900 mt-1">Prakrita</p>
                <p className="text-[11px] text-slate-500">Clear yellow; no dysuria</p>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[10px] font-bold text-slate-600 uppercase">8. Akriti (Build)</span>
                <p className="text-xs font-bold text-slate-900 mt-1">Madhyama</p>
                <p className="text-[11px] text-slate-500">Moderate constitutional frame</p>
              </div>
            </div>
          </div>
        )}

        {/* 3. Ayush Chikitsa Guidance View with Color-Coded Formulation Badges */}
        {activeSubTab === 'chikitsa' && !matchedRoga && (
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-6 text-center">
            <p className="text-sm font-semibold text-slate-700">No Chikitsa guidance for this complaint</p>
            <p className="mt-1 text-xs text-slate-500 max-w-md mx-auto">
              The formulations, doses and Pathya/Apathya below are a fixed mapping
              from a small set of complaints. This patient's complaint is not one
              of them, and showing the default would name three medicines with
              doses for a condition nobody suspected.
            </p>
          </div>
        )}

        {activeSubTab === 'chikitsa' && matchedRoga && (
          <div className="space-y-3.5">
            <div className="bg-teal-50/40 border border-teal-200/80 rounded-xl p-3.5">
              <span className="text-[11px] font-bold text-teal-900 uppercase tracking-wide flex items-center gap-1.5 mb-1.5">
                <Leaf className="w-3.5 h-3.5 text-teal-700" />
                Kayachikitsa Treatment Principles (Chikitsa Sutra)
              </span>
              <p className="text-xs text-teal-950 leading-relaxed font-medium">
                {chikitsaPrinciple}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="bg-amber-50/40 border border-amber-200/80 rounded-xl p-3">
                <span className="text-[10px] font-bold text-amber-800 uppercase">{formulation1.role}</span>
                <p className="text-xs font-bold text-amber-950 mt-1">{formulation1.name}</p>
                <p className="text-[11px] text-slate-600 mt-1">{formulation1.dose}</p>
              </div>

              <div className="bg-emerald-50/40 border border-emerald-200/80 rounded-xl p-3">
                <span className="text-[10px] font-bold text-emerald-800 uppercase">{formulation2.role}</span>
                <p className="text-xs font-bold text-emerald-950 mt-1">{formulation2.name}</p>
                <p className="text-[11px] text-slate-600 mt-1">{formulation2.dose}</p>
              </div>

              <div className="bg-sky-50/40 border border-sky-200/80 rounded-xl p-3">
                <span className="text-[10px] font-bold text-sky-800 uppercase">{formulation3.role}</span>
                <p className="text-xs font-bold text-sky-950 mt-1">{formulation3.name}</p>
                <p className="text-[11px] text-slate-600 mt-1">{formulation3.dose}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
