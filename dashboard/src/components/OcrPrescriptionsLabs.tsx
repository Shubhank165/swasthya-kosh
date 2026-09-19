import React, { useState } from 'react';
import { 
  FileSearch, 
  ClipboardList
} from 'lucide-react';
import { IntakeData } from '../types';

interface OcrPrescriptionsLabsProps {
  currentData: IntakeData;
}

export const OcrPrescriptionsLabs: React.FC<OcrPrescriptionsLabsProps> = ({ currentData }) => {
  const [selectedScan, setSelectedScan] = useState<'prescription' | 'blood_report'>('prescription');

  const fields = currentData.fields;
  const ocrMed = fields.current_medications;
  const labSugar = fields.lab_sugar;
  const labHbsag = fields.lab_hbsag;
  const labHiv = fields.lab_hiv;
  const labHb = fields.lab_hemoglobin;

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 bg-slate-50/80 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center">
            <FileSearch className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <span>Diagnostic Scans & Lab Investigations (OCR)</span>
              <span className="text-[10px] font-bold bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full border border-indigo-200">
                Kiosk Camera OCR
              </span>
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-lg text-xs">
          <button
            type="button"
            onClick={() => setSelectedScan('prescription')}
            className={`px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer ${
              selectedScan === 'prescription'
                ? 'bg-white text-indigo-700 shadow-2xs font-semibold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Prescription Slip
          </button>
          <button
            type="button"
            onClick={() => setSelectedScan('blood_report')}
            className={`px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer ${
              selectedScan === 'blood_report'
                ? 'bg-white text-indigo-700 shadow-2xs font-semibold'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Lab Reports (5)
          </button>
        </div>
      </div>

      <div className="p-5">
        {/* Extracted Labs & Medical History */}
        <div className="space-y-3.5">
          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wide flex items-center gap-1.5">
            <ClipboardList className="w-3.5 h-3.5 text-teal-600" />
            <span>Extracted Diagnostic Labs & Confidence Scores</span>
          </h4>

            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="min-w-full text-xs divide-y divide-slate-200">
                <thead className="bg-slate-50 text-slate-600 font-semibold">
                  <tr>
                    <th className="py-2.5 px-3 text-left">Test / Marker</th>
                    <th className="py-2.5 px-3 text-left">Detected Value</th>
                    <th className="py-2.5 px-3 text-left">OCR Conf</th>
                    <th className="py-2.5 px-3 text-right">Clinical Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {/* Blood Sugar */}
                  <tr>
                    <td className="py-2.5 px-3 font-semibold text-slate-800">
                      Blood Sugar (Random)
                    </td>
                    <td className="py-2.5 px-3 text-slate-700 font-mono">
                      103 mg/dL ({labSugar?.original_text || 'सुगर- १०३'})
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1.5">
                        <div className="w-12 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                          <div className="bg-amber-500 h-1.5 rounded-full" style={{ width: '70%' }}></div>
                        </div>
                        <span className="text-[11px] text-slate-500 font-mono">70%</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className="text-[10px] font-semibold bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full">
                        Normal (70-140)
                      </span>
                    </td>
                  </tr>

                  {/* Hemoglobin */}
                  <tr>
                    <td className="py-2.5 px-3 font-semibold text-slate-800">
                      Hemoglobin (Hb)
                    </td>
                    <td className="py-2.5 px-3 text-slate-500 italic">
                      Marker noted (numerical unread)
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1.5">
                        <div className="w-12 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                          <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: '90%' }}></div>
                        </div>
                        <span className="text-[11px] text-slate-500 font-mono">90%</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className="text-[10px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                        Needs Fresh CBC
                      </span>
                    </td>
                  </tr>

                  {/* HBsAg */}
                  <tr>
                    <td className="py-2.5 px-3 font-semibold text-slate-800">
                      HBsAg
                    </td>
                    <td className="py-2.5 px-3 text-slate-700 font-mono">
                      60 (Value scanned)
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1.5">
                        <div className="w-12 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                          <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: '80%' }}></div>
                        </div>
                        <span className="text-[11px] text-slate-500 font-mono">80%</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className="text-[10px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                        Check Reference
                      </span>
                    </td>
                  </tr>

                  {/* HIV */}
                  <tr>
                    <td className="py-2.5 px-3 font-semibold text-slate-800">
                      HIV Screening
                    </td>
                    <td className="py-2.5 px-3 text-slate-700 font-mono">
                      {labHiv?.original_text || 'बी.वी.- ११०'}
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1.5">
                        <div className="w-12 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                          <div className="bg-amber-500 h-1.5 rounded-full" style={{ width: '75%' }}></div>
                        </div>
                        <span className="text-[11px] text-slate-500 font-mono">75%</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className="text-[10px] font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                        Routine Pre-op
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    );
  };
