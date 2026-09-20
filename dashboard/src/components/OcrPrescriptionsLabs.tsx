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

  /**
   * Lab rows, built from what OCR actually read.
   *
   * These four used to be literal `<tr>`s — "103 mg/dL", "Normal (70-140)",
   * "Needs Fresh CBC" — rendered for every patient whether or not a scan
   * existed. A fabricated lab result on a physician's screen is worse than an
   * empty table, so a row appears only when its fact does, the number shown is
   * the backend's own rendering of it, and a marker that was seen but not read
   * says exactly that instead of borrowing a plausible value.
   *
   * No clinical verdict is drawn here. "Normal (70-140)" is a reference-range
   * judgement this dashboard is not allowed to make — the README's rule is that
   * clinical content arrives decided — so the last column carries the patient's
   * own words instead, which is evidence rather than interpretation.
   */
  const LAB_FIELDS: Array<{ fieldId: string; label: string }> = [
    { fieldId: 'lab_sugar', label: 'Blood sugar' },
    { fieldId: 'lab_fbs/rbs', label: 'Fasting / random blood sugar' },
    { fieldId: 'lab_hemoglobin', label: 'Haemoglobin (Hb)' },
    { fieldId: 'lab_hbsag', label: 'HBsAg' },
    { fieldId: 'lab_hiv', label: 'HIV screening' },
    { fieldId: 'lab_widal_test', label: 'Widal test' },
    { fieldId: 'lab_malaria_parasite', label: 'Malaria parasite' },
    { fieldId: 'lab_sputum_for_afb/bs', label: 'Sputum for AFB / BS' },
  ];

  const labRows = LAB_FIELDS.flatMap(({ fieldId, label }) => {
    const item = fields[fieldId];
    if (!item || item.status !== 'answered') return [];
    const value = item.value;
    const detected =
      value?.text ??
      (value?.magnitude !== undefined
        ? `${value.magnitude}${value.unit ? ` ${value.unit}` : ''}`
        : undefined);
    return [{
      fieldId,
      label,
      detected: detected ?? null,
      confidence: item.confidence ?? null,
      verbatim: item.original_text ?? null,
      language: item.language ?? null,
    }];
  });

  // What the patient actually attached, as opposed to what OCR made of it. The
  // two come apart: a scan can be on the record with its reading still pending,
  // and the lab rows below can be empty while a prescription is sitting right
  // there. Saying which of those is the case is the difference between "nothing
  // was brought" and "nothing has been read yet".
  const documents = currentData.documents ?? [];
  const readingPending = documents.some(
    (doc) => doc.status !== undefined && doc.status !== 'read' && doc.status !== 'complete',
  );

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

      {/* What was attached, before anything is claimed about its contents. */}
      <div className="px-5 py-2.5 border-b border-slate-100 bg-white flex items-center gap-2 flex-wrap text-xs">
        <span className="font-semibold text-slate-700">Attached scans</span>
        {documents.length === 0 ? (
          <span className="text-slate-500">
            None on this record — nothing was uploaded for this visit.
          </span>
        ) : (
          documents.map((doc) => (
            <span
              key={doc.document_id}
              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-slate-200 bg-slate-50 text-slate-700"
            >
              <span className="font-medium capitalize">{doc.kind.replace(/_/g, ' ')}</span>
              {doc.status && <span className="text-slate-400">· {doc.status}</span>}
            </span>
          ))
        )}
        {readingPending && (
          <span className="text-amber-700">Reading still in progress — values below may be incomplete.</span>
        )}
      </div>
      </div>

      <div className="p-5">
        {/* Extracted Labs & Medical History */}
        <div className="space-y-3.5">
          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wide flex items-center gap-1.5">
            <ClipboardList className="w-3.5 h-3.5 text-teal-600" />
            <span>Extracted Diagnostic Labs & Confidence Scores</span>
          </h4>

            {labRows.length === 0 ? (
              <div className="border border-slate-200 rounded-xl px-4 py-6 text-center">
                <p className="text-sm font-semibold text-slate-700">No lab values on this record</p>
                <p className="mt-1 text-xs text-slate-500">
                  {documents.length === 0
                    ? 'Nothing was scanned for this visit.'
                    : 'A scan is attached but no numbers have been read from it yet.'}
                </p>
              </div>
            ) : (
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="min-w-full text-xs divide-y divide-slate-200">
                <thead className="bg-slate-50 text-slate-600 font-semibold">
                  <tr>
                    <th className="py-2.5 px-3 text-left">Test / Marker</th>
                    <th className="py-2.5 px-3 text-left">Detected value</th>
                    <th className="py-2.5 px-3 text-left">OCR confidence</th>
                    <th className="py-2.5 px-3 text-right">Patient's own words</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {labRows.map((row) => (
                    <tr key={row.fieldId}>
                      <td className="py-2.5 px-3 font-semibold text-slate-800">{row.label}</td>
                      <td className="py-2.5 px-3 text-slate-700 font-mono">
                        {row.detected ?? (
                          <span className="text-slate-400 italic font-sans">
                            marker noted, value unread
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3">
                        {row.confidence === null ? (
                          <span className="text-slate-400">not reported</span>
                        ) : (
                          <div className="flex items-center gap-1.5">
                            <div className="w-12 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="bg-teal-500 h-1.5 rounded-full"
                                style={{ width: `${Math.round(row.confidence * 100)}%` }}
                              />
                            </div>
                            <span className="text-[11px] text-slate-500 font-mono">
                              {Math.round(row.confidence * 100)}%
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right text-slate-600" lang={row.language ?? undefined}>
                        {row.verbatim ?? '\u2014'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
          </div>
        </div>
      </div>
    );
  };
