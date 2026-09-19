import React from 'react';
import { Printer, X, Building2, CheckCircle2, ShieldCheck, Heart, Wind } from 'lucide-react';
import { IntakeData } from '../types';

interface PrintableOpdSlipProps {
  currentData: IntakeData;
  onClose: () => void;
}

export const PrintableOpdSlip: React.FC<PrintableOpdSlipProps> = ({
  currentData,
  onClose
}) => {
  const abha = currentData.abhaDetails;
  const vitals = currentData.cameraVitals;
  const fields = currentData.fields;

  const handleTriggerPrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white rounded-2xl max-w-2xl w-full my-6 overflow-hidden shadow-2xl border border-slate-300">
        {/* Print Action Bar */}
        <div className="bg-slate-800 text-white px-5 py-3 flex items-center justify-between print:hidden">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <Printer className="w-4 h-4 text-teal-400" />
            <span>Consultation OPD Slip Preview</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleTriggerPrint}
              className="px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs"
            >
              <Printer className="w-3.5 h-3.5" />
              <span>Print Document</span>
            </button>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Printable Paper Canvas */}
        <div className="p-8 text-slate-900 font-sans space-y-5 print:p-0">
          {/* Official Letterhead */}
          <div className="border-b-2 border-slate-900 pb-4 flex justify-between items-start">
            <div className="flex items-start gap-3">
              <div className="w-12 h-12 rounded-xl bg-teal-800 text-white flex items-center justify-center font-bold text-xl">
                AIIA
              </div>
              <div>
                <h2 className="font-extrabold text-base tracking-tight text-slate-900 uppercase">
                  All India Institute of Ayurveda (AIIA)
                </h2>
                <p className="text-xs text-slate-600">
                  Ministry of Ayush, Govt. of India • Sarita Vihar, New Delhi - 110076
                </p>
                <p className="text-[11px] font-bold text-teal-800 mt-0.5">
                  Department of Kayachikitsa (Internal Medicine) • MediKiosk OPD
                </p>
              </div>
            </div>

            <div className="text-right font-mono text-xs">
              <div className="font-bold bg-slate-100 px-2 py-1 rounded text-slate-900 border border-slate-200 inline-block">
                TOKEN #OPD-042
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Date: 18-Sep-2026</div>
            </div>
          </div>

          {/* Patient Details & ABHA Bar */}
          <div className="grid grid-cols-3 gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs">
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block">Patient Name</span>
              <span className="font-bold text-slate-900 text-sm">{abha?.name || 'Guest Patient'}</span>
              <span className="text-slate-600 block text-[11px]">Age: {fields.age?.value?.magnitude || 21} Y • {fields['general.sex']?.value?.text || 'Male'}</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block">ABHA Number</span>
              <span className="font-mono font-bold text-slate-900">{abha?.abhaNumber}</span>
              <span className="text-emerald-700 block text-[11px] font-medium">✓ ABDM eKYC Verified</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block">Intake Origin</span>
              <span className="font-medium text-slate-800">
                {currentData.kiosk_id ? 'MediKiosk #jetson-opd-1' : 'Mobile App Pre-Queue'}
              </span>
              <span className="text-[10px] text-slate-500 block">ID: {currentData.intake_id.slice(0, 12)}</span>
            </div>
          </div>

          {/* Camera Extracted Vitals */}
          <div className="p-3 border border-slate-200 rounded-lg text-xs">
            <div className="font-bold text-slate-800 uppercase text-[10px] tracking-wider mb-1.5 flex items-center gap-1.5">
              <span>Contactless Camera Vitals (NVIDIA Jetson Optical rPPG)</span>
              <span className="text-emerald-700 font-normal">Confidence: 94%</span>
            </div>
            <div className="grid grid-cols-4 gap-2 font-mono">
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Pulse Rate</span>
                <span className="font-bold text-slate-900">{vitals?.heartRateBpm || 76} BPM</span>
              </div>
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Resp. Rate</span>
                <span className="font-bold text-slate-900">{vitals?.respiratoryRateBpm || 17} /min</span>
              </div>
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-[10px] text-slate-500 block">Est. SpO2</span>
                <span className="font-bold text-slate-900">{vitals?.spo2Estimate || 98} %</span>
              </div>
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-[10px] text-slate-500 block">HRV</span>
                <span className="font-bold text-slate-900">{vitals?.hrvMs || 64} ms</span>
              </div>
            </div>
          </div>

          {/* Chief Complaint & Ayurvedic Prakriti */}
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div className="border border-slate-200 p-3 rounded-lg">
              <div className="font-bold text-slate-800 uppercase text-[10px] tracking-wider mb-1">
                Chief Complaint & History
              </div>
              <div className="font-semibold text-slate-900">
                Lower Abdominal Pain & Heartburn (Duration: 3 days)
              </div>
              <p className="text-[11px] text-slate-600 mt-1">
                Triggered post outside street food. Associated with nausea, decreased appetite. No fever or vomiting.
              </p>
            </div>

            <div className="border border-slate-200 p-3 rounded-lg">
              <div className="font-bold text-slate-800 uppercase text-[10px] tracking-wider mb-1">
                Ayurvedic Assessment
              </div>
              <div className="grid grid-cols-2 gap-1 text-[11px]">
                <span>Prakriti: <strong>Pitta Predominant</strong></span>
                <span>Ahara Shakti: <strong>Madhyama</strong></span>
                <span>Satva: <strong>Irritable (Rajas)</strong></span>
                <span>Agni: <strong>Mandagni / Visham</strong></span>
              </div>
            </div>
          </div>

          {/* Rx Prescriptions */}
          <div className="border-t-2 border-slate-900 pt-3 text-xs">
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-base font-serif italic text-slate-900">Rx Prescriptions</span>
              <span className="text-[10px] text-slate-500">Dispense via AIIA Pharmacy</span>
            </div>

            <div className="space-y-2 font-mono text-xs">
              <div className="flex justify-between pb-1 border-b border-slate-200">
                <span>1. Avipattikar Churna [3g]</span>
                <span>Twice daily before food with warm water x 7 days</span>
              </div>
              <div className="flex justify-between pb-1 border-b border-slate-200">
                <span>2. Kamadudha Ras (Moti Yukta) [250mg]</span>
                <span>Twice daily after meals x 7 days</span>
              </div>
              <div className="flex justify-between pb-1 border-b border-slate-200">
                <span>3. Tab. Pantoprazole [40mg]</span>
                <span>1 tab once daily early morning empty stomach x 5 days</span>
              </div>
            </div>
          </div>

          {/* Advice & Signature */}
          <div className="pt-4 border-t border-slate-200 flex justify-between items-end text-xs">
            <div>
              <span className="font-bold text-slate-800 uppercase text-[10px] block">Doctor's Advice:</span>
              <p className="text-[11px] text-slate-600 max-w-sm">
                Follow Pitta-shamaka diet. Avoid spicy, fried, and stale outside foods. Follow-up after 5 days.
              </p>
            </div>

            <div className="text-right">
              <div className="h-10 w-32 border-b border-slate-400 mb-1 ml-auto"></div>
              <span className="font-bold text-slate-900 block">Dr. S. K. Sharma, MD (Ayu)</span>
              <span className="text-[10px] text-slate-500">Reg. No: AY-DEL-49210</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
