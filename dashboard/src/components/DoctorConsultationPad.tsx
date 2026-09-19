import React, { useState } from 'react';
import { 
  Stethoscope, 
  Pill, 
  Plus, 
  Trash2, 
  Printer, 
  Save, 
  Check, 
  FileCheck, 
  Sparkles,
  Calendar,
  AlertCircle
} from 'lucide-react';
import { IntakeData, DoctorNote } from '../types';

interface DoctorConsultationPadProps {
  currentData: IntakeData;
  onPrint: () => void;
}

export const DoctorConsultationPad: React.FC<DoctorConsultationPadProps> = ({
  currentData,
  onPrint
}) => {
  const [diagnosis, setDiagnosis] = useState(
    'Acute Dyspepsia / Amlapitta (Secondary to Dietary Indiscretion)'
  );
  const [doctorNotes, setDoctorNotes] = useState(
    'Patient presents with 3-day history of worsening epigastric & lower abdominal distress post outside food consumption. Associated with nausea & acidity. Vitals stable via camera rPPG. No fever or gastrointestinal bleeding. Advised light warm Pitta-pacifying diet and avoidance of fried/spicy foods.'
  );

  const [prescriptions, setPrescriptions] = useState([
    {
      name: 'Avipattikar Churna',
      dosage: '3 grams',
      timing: 'Twice daily with lukewarm water before food',
      duration: '7 days'
    },
    {
      name: 'Kamadudha Ras (Moti Yukta)',
      dosage: '1 tablet (250mg)',
      timing: 'Twice daily after meals with milk/water',
      duration: '7 days'
    },
    {
      name: 'Tab. Pantoprazole 40 mg',
      dosage: '1 tab',
      timing: 'Once daily empty stomach early morning',
      duration: '5 days'
    }
  ]);

  const [newMedName, setNewMedName] = useState('');
  const [newMedDosage, setNewMedDosage] = useState('');
  const [newMedTiming, setNewMedTiming] = useState('Twice daily');
  const [newMedDuration, setNewMedDuration] = useState('5 days');

  const [orderedLabs, setOrderedLabs] = useState<string[]>([
    'USG Whole Abdomen (Screening)',
    'CBC (Complete Blood Count)'
  ]);

  const [followUpDate, setFollowUpDate] = useState('After 5 days (OPD Room 4)');
  const [isSaved, setIsSaved] = useState(false);

  const handleAddMed = () => {
    if (!newMedName.trim()) return;
    setPrescriptions((prev) => [
      ...prev,
      {
        name: newMedName.trim(),
        dosage: newMedDosage.trim() || '1 tab',
        timing: newMedTiming,
        duration: newMedDuration
      }
    ]);
    setNewMedName('');
    setNewMedDosage('');
  };

  const handleRemoveMed = (index: number) => {
    setPrescriptions((prev) => prev.filter((_, i) => i !== index));
  };

  const toggleLab = (lab: string) => {
    if (orderedLabs.includes(lab)) {
      setOrderedLabs((prev) => prev.filter((l) => l !== lab));
    } else {
      setOrderedLabs((prev) => [...prev, lab]);
    }
  };

  const handleSaveNote = () => {
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 3000);
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 bg-gradient-to-r from-teal-900/5 via-slate-50 to-indigo-900/5 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-teal-700 text-white flex items-center justify-center font-bold text-xs shadow-xs">
            <Stethoscope className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <span>Doctor's Consultation & Rx Pad</span>
              <span className="text-[10px] font-bold bg-teal-100 text-teal-800 px-2 py-0.5 rounded-full">
                Active EMR
              </span>
            </h3>
            <p className="text-[11px] text-slate-500">
              Formulate diagnosis, prescribe Ayurvedic & Allopathic treatments, and order investigations
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSaveNote}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all ${
              isSaved
                ? 'bg-emerald-600 text-white shadow-xs'
                : 'bg-teal-600 hover:bg-teal-700 text-white shadow-xs'
            }`}
          >
            {isSaved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
            <span>{isSaved ? 'Consultation Saved' : 'Save Prescription'}</span>
          </button>

          <button
            type="button"
            onClick={onPrint}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold border border-slate-300 hover:bg-slate-50 text-slate-700 flex items-center gap-1.5 transition-colors shadow-2xs"
          >
            <Printer className="w-3.5 h-3.5" />
            <span>Print OPD Slip</span>
          </button>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Provisional Diagnosis */}
        <div>
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">
            Provisional Diagnosis / Differential
          </label>
          <input
            type="text"
            value={diagnosis}
            onChange={(e) => setDiagnosis(e.target.value)}
            className="w-full text-sm font-semibold text-slate-900 border border-slate-200 rounded-xl px-3.5 py-2.5 focus:outline-hidden focus:ring-2 focus:ring-teal-500 bg-slate-50/50"
            placeholder="e.g. Acute Dyspepsia / Amlapitta"
          />
        </div>

        {/* Prescription List */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-bold text-slate-700 uppercase tracking-wide flex items-center gap-1.5">
              <Pill className="w-3.5 h-3.5 text-teal-600" />
              <span>Prescribed Medications (Rx)</span>
            </label>
            <span className="text-[11px] text-slate-400">
              Integrated Ayurveda + Modern Supportive
            </span>
          </div>

          <div className="space-y-2">
            {prescriptions.map((rx, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-3 rounded-xl border border-slate-200/80 bg-slate-50/50 text-xs gap-3 flex-wrap sm:flex-nowrap"
              >
                <div className="flex items-center gap-3">
                  <span className="w-5 h-5 rounded-full bg-teal-100 text-teal-800 flex items-center justify-center font-bold text-[11px] shrink-0">
                    {idx + 1}
                  </span>
                  <div>
                    <span className="font-bold text-slate-900 text-sm">{rx.name}</span>
                    <span className="text-slate-500 font-mono ml-2">[{rx.dosage}]</span>
                    <div className="text-[11px] text-slate-600 mt-0.5">
                      {rx.timing} • <span className="font-medium text-teal-700">{rx.duration}</span>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => handleRemoveMed(idx)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors ml-auto"
                  title="Remove medication"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>

          {/* Add Medicine Row */}
          <div className="mt-3 p-3 rounded-xl border border-dashed border-slate-300 bg-slate-50/40 grid grid-cols-1 sm:grid-cols-4 gap-2 items-center">
            <input
              type="text"
              placeholder="Drug name (e.g. Shankha Bhasma)"
              value={newMedName}
              onChange={(e) => setNewMedName(e.target.value)}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white"
            />
            <input
              type="text"
              placeholder="Dosage (e.g. 250mg)"
              value={newMedDosage}
              onChange={(e) => setNewMedDosage(e.target.value)}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white"
            />
            <input
              type="text"
              placeholder="Timing (e.g. BD after food)"
              value={newMedTiming}
              onChange={(e) => setNewMedTiming(e.target.value)}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white"
            />
            <button
              type="button"
              onClick={handleAddMed}
              className="px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white font-semibold text-xs flex items-center justify-center gap-1 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Rx</span>
            </button>
          </div>
        </div>

        {/* Recommended Investigations */}
        <div>
          <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">
            Diagnostic Investigations to Order
          </label>
          <div className="flex flex-wrap gap-2">
            {[
              'USG Whole Abdomen (Screening)',
              'CBC (Complete Blood Count)',
              'Serum Amylase & Lipase',
              'Liver Function Test (LFT)',
              'Urine Routine & Microscopic',
              'Stool Occult Blood (FOBT)'
            ].map((lab) => {
              const isChecked = orderedLabs.includes(lab);
              return (
                <button
                  key={lab}
                  type="button"
                  onClick={() => toggleLab(lab)}
                  className={`text-xs px-3 py-1.5 rounded-xl border font-medium transition-all ${
                    isChecked
                      ? 'bg-teal-50 border-teal-300 text-teal-800 font-semibold'
                      : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {isChecked ? '✓ ' : '+ '}
                  {lab}
                </button>
              );
            })}
          </div>
        </div>

        {/* Doctor Clinical Notes & Follow-Up */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">
              Doctor Clinical Notes & Advice
            </label>
            <textarea
              rows={3}
              value={doctorNotes}
              onChange={(e) => setDoctorNotes(e.target.value)}
              className="w-full text-xs text-slate-800 border border-slate-200 rounded-xl p-3 focus:outline-hidden focus:ring-2 focus:ring-teal-500 bg-slate-50/50"
              placeholder="Clinical instructions, diet advice, warning symptoms..."
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1.5">
              Follow-Up Instruction
            </label>
            <input
              type="text"
              value={followUpDate}
              onChange={(e) => setFollowUpDate(e.target.value)}
              className="w-full text-xs text-slate-800 border border-slate-200 rounded-xl p-3 focus:outline-hidden focus:ring-2 focus:ring-teal-500 bg-slate-50/50"
              placeholder="e.g. In 5 days or SOS"
            />
            <div className="text-[10px] text-slate-400 mt-2 flex items-center gap-1">
              <Calendar className="w-3 h-3 text-teal-600" />
              <span>Auto-appends to OPD slip & patient SMS</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
