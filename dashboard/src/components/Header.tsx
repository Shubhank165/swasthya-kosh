import React from 'react';
import { IntakeData } from '../types';
import { 
  Building2, 
  ShieldCheck, 
  Smartphone, 
  Monitor, 
  Printer, 
  FileText, 
  CheckCircle2, 
  UserCheck, 
  Sparkles,
  RefreshCw,
  QrCode,
  ArrowLeft,
  ArrowRight,
  Users
} from 'lucide-react';

interface HeaderProps {
  currentData: IntakeData;
  onBackToQueue: () => void;
  onNextPatient?: () => void;
  onPrint: () => void;
  onToggleAbhaModal: () => void;
  statusText: string;
  onChangeStatusText: (status: string) => void;
  patientToken?: string;
  hasNextPatient?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  currentData,
  onBackToQueue,
  onNextPatient,
  onPrint,
  onToggleAbhaModal,
  statusText,
  onChangeStatusText,
  patientToken = '#OPD-042',
  hasNextPatient = false
}) => {
  const abha = currentData.abhaDetails;
  const isKiosk = currentData.kiosk_id !== null || currentData.source === 'kiosk';

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
      {/* Top hospital & OPD brand bar */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-2.5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBackToQueue}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition-colors shadow-2xs group"
            title="Return to OPD Patient Queue"
          >
            <ArrowLeft className="w-3.5 h-3.5 transition-transform group-hover:-translate-x-0.5 text-slate-600" />
            <span>OPD Queue List</span>
          </button>

          <div className="w-9 h-9 rounded-xl bg-teal-600 flex items-center justify-center text-white shadow-xs">
            <Building2 className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-semibold text-slate-900 text-base leading-tight">
                All India Institute of Ayurveda (AIIA), Delhi
              </h1>
              <span className="text-[11px] font-medium bg-teal-50 text-teal-700 px-2 py-0.5 rounded-full border border-teal-200">
                Kayachikitsa OPD
              </span>
            </div>
          </div>
        </div>

        {/* Doctor Actions */}
        <div className="flex items-center gap-2.5">
          {/* Patient Intake Source Tag */}
          <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-xl bg-slate-100 text-xs font-medium text-slate-700 border border-slate-200">
            {isKiosk ? (
              <>
                <Monitor className="w-3.5 h-3.5 text-teal-600" />
                <span>Intake: <strong>MediKiosk Terminal ({currentData.kiosk_id || 'jetson-opd-1'})</strong></span>
              </>
            ) : (
              <>
                <Smartphone className="w-3.5 h-3.5 text-indigo-600" />
                <span>Intake: <strong>Mobile App Pre-Queue</strong></span>
              </>
            )}
          </div>

          {hasNextPatient && onNextPatient && (
            <button
              id="btn-next-patient"
              type="button"
              onClick={onNextPatient}
              className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-teal-50 hover:bg-teal-100 text-teal-800 border border-teal-200 text-xs font-semibold transition-colors"
              title="Save and advance to next patient in queue"
            >
              <span>Next Patient</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}

          <button
            id="btn-print-slip"
            type="button"
            onClick={onPrint}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors shadow-xs"
            title="Print Consultation OPD Slip"
          >
            <Printer className="w-3.5 h-3.5 text-slate-500" />
            <span className="hidden sm:inline">Print OPD Slip</span>
          </button>
        </div>
      </div>

      {/* Patient Primary Demographic & ABHA Strip */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="text-xs font-bold bg-teal-50 border border-teal-200 text-teal-900 px-2.5 py-1 rounded-lg font-mono tracking-wide shadow-2xs">
                TOKEN {patientToken}
              </span>
              <h2 className="text-lg font-bold text-slate-900">
                {abha?.name || 'Guest Patient'}
              </h2>
              <span className="text-xs text-slate-500 font-medium">
                {currentData.fields.age?.value?.magnitude || 21} Y / {currentData.fields['general.sex']?.value?.text || 'Male'}
              </span>

              {/* ABHA Badge */}
              {abha?.verified ? (
                <button
                  onClick={onToggleAbhaModal}
                  className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200 hover:bg-emerald-100 transition-colors"
                >
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  <span>ABHA Verified: {abha.abhaNumber}</span>
                  <QrCode className="w-3 h-3 text-emerald-700 ml-0.5" />
                </button>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-amber-50 text-amber-800 border border-amber-200">
                  ABHA Pending Verification
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Quick Triage Status & Severity Indicator */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 flex items-center gap-3">
            <div className="text-right">
              <div className="text-[10px] text-slate-400 uppercase font-semibold">Triage Pain Severity</div>
              <div className="text-sm font-bold text-slate-800 flex items-center justify-end gap-1.5">
                <span className="text-rose-600">
                  {currentData.fields['general.severity']?.value?.value ?? currentData.fields.severity?.value?.value ?? 7}/10
                </span>
                <span className="text-[11px] font-normal text-slate-500">
                  {(Number(currentData.fields['general.severity']?.value?.value ?? currentData.fields.severity?.value?.value ?? 7) >= 7) ? 'Moderate-Severe' : 'Mild'}
                </span>
              </div>
            </div>
            <div className={`w-3 h-3 rounded-full ${
              (Number(currentData.fields['general.severity']?.value?.value ?? currentData.fields.severity?.value?.value ?? 7) >= 7) 
                ? 'bg-rose-500 animate-pulse' 
                : 'bg-emerald-500'
            }`} />
          </div>

          <select
            id="select-consultation-status"
            value={statusText}
            onChange={(e) => onChangeStatusText(e.target.value)}
            className="text-xs font-semibold bg-teal-50 text-teal-800 border border-teal-300 rounded-xl px-3 py-2 cursor-pointer focus:outline-hidden focus:ring-2 focus:ring-teal-500 shadow-2xs"
          >
            <option value="in_consultation">🩺 In Consultation</option>
            <option value="waiting">⏳ Waiting in Queue</option>
            <option value="labs_ordered">🧪 Labs Ordered</option>
            <option value="completed">✅ Consultation Complete</option>
          </select>
        </div>
      </div>
    </header>
  );
};

