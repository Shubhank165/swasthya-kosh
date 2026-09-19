import React from 'react';
import { 
  ShieldCheck, 
  X, 
  QrCode, 
  Building, 
  Calendar, 
  User, 
  FileCheck2, 
  CheckCircle2, 
  ExternalLink 
} from 'lucide-react';
import { IntakeData } from '../types';

interface AbhaDetailsModalProps {
  currentData: IntakeData;
  onClose: () => void;
}

export const AbhaDetailsModal: React.FC<AbhaDetailsModalProps> = ({
  currentData,
  onClose
}) => {
  const abha = currentData.abhaDetails;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
      <div className="bg-white rounded-2xl max-w-lg w-full overflow-hidden shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="bg-gradient-to-r from-emerald-800 to-teal-800 text-white p-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-emerald-300" />
            </div>
            <div>
              <h3 className="font-bold text-base leading-tight">
                Ayushman Bharat Health Account (ABHA)
              </h3>
              <p className="text-xs text-emerald-100">
                National Health Authority (NHA) • ABDM Gateway Verified
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5">
          {/* Card Mockup */}
          <div className="rounded-2xl border-2 border-emerald-500/30 bg-gradient-to-br from-emerald-50/70 via-teal-50/50 to-slate-50 p-5 relative overflow-hidden shadow-xs">
            <div className="flex justify-between items-start">
              <div className="flex items-center gap-3">
                {abha?.photoUrl ? (
                  <img
                    src={abha.photoUrl}
                    alt={abha.name}
                    className="w-14 h-14 rounded-xl object-cover border-2 border-white shadow-xs"
                  />
                ) : (
                  <div className="w-14 h-14 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold text-xl">
                    {abha?.name?.[0] || 'P'}
                  </div>
                )}
                <div>
                  <h4 className="font-bold text-slate-900 text-base">{abha?.name}</h4>
                  <div className="text-xs text-slate-600 font-mono">
                    DOB: {abha?.dob} • {abha?.gender}
                  </div>
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-100/80 px-2 py-0.5 rounded-md mt-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                    eKYC Aadhaar Verified
                  </span>
                </div>
              </div>

              {/* QR Code mock */}
              <div className="w-16 h-16 bg-white p-1 rounded-lg border border-slate-200 shadow-2xs flex flex-col items-center justify-center">
                <QrCode className="w-12 h-12 text-slate-800" />
                <span className="text-[8px] font-mono text-slate-400">SCAN ABDM</span>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-emerald-200/60 grid grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-[10px] text-slate-500 uppercase tracking-wide block font-semibold">
                  ABHA Number (14 Digits)
                </span>
                <span className="font-mono font-bold text-slate-900 text-sm tracking-wider">
                  {abha?.abhaNumber}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 uppercase tracking-wide block font-semibold">
                  ABHA Address
                </span>
                <span className="font-mono font-bold text-teal-800 text-xs">
                  {abha?.abhaAddress}
                </span>
              </div>
            </div>
          </div>

          {/* Linked Records List */}
          <div>
            <h5 className="text-xs font-bold text-slate-900 uppercase tracking-wide mb-2 flex items-center justify-between">
              <span>Linked Health Facilities (ABDM Grid)</span>
              <span className="text-emerald-700 font-medium text-[11px]">
                {abha?.linkedHealthRecords || 3} Linked Repositories
              </span>
            </h5>

            <div className="space-y-2 text-xs">
              <div className="p-2.5 rounded-xl border border-slate-200 bg-slate-50/60 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Building className="w-4 h-4 text-teal-600" />
                  <div>
                    <span className="font-semibold text-slate-800 block">All India Institute of Ayurveda, Delhi</span>
                    <span className="text-[10px] text-slate-500">Current OPD Visit • Kayachikitsa</span>
                  </div>
                </div>
                <span className="text-[10px] font-mono text-emerald-600 font-semibold bg-emerald-50 px-2 py-0.5 rounded">
                  Active
                </span>
              </div>

              <div className="p-2.5 rounded-xl border border-slate-200 bg-slate-50/60 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Building className="w-4 h-4 text-slate-500" />
                  <div>
                    <span className="font-semibold text-slate-800 block">AIIMS New Delhi</span>
                    <span className="text-[10px] text-slate-500">Past General Lab Panels (Aug 2025)</span>
                  </div>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">Consented</span>
              </div>

              <div className="p-2.5 rounded-xl border border-slate-200 bg-slate-50/60 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Building className="w-4 h-4 text-slate-500" />
                  <div>
                    <span className="font-semibold text-slate-800 block">Safdarjung Hospital</span>
                    <span className="text-[10px] text-slate-500">Outpatient Consultation (Jan 2026)</span>
                  </div>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">Consented</span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="bg-slate-50 px-6 py-3 border-t border-slate-100 flex items-center justify-between text-xs">
          <span className="text-[11px] text-slate-500">
            Digital Personal Data Protection (DPDP) Act Compliant
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-900 text-white font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
