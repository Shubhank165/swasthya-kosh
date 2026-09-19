import React from 'react';
import { Camera, Activity, Wind, Heart, CheckCircle } from 'lucide-react';
import { IntakeData } from '../types';

interface VitalsStationProps {
  currentData: IntakeData;
}

export const VitalsStation: React.FC<VitalsStationProps> = ({ currentData }) => {
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
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-2xs overflow-hidden">
      {/* Station Header - Compact */}
      <div className="px-4 py-2.5 bg-gradient-to-r from-teal-50/70 via-slate-50 to-emerald-50/60 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-teal-100 text-teal-700 flex items-center justify-center shrink-0">
            <Camera className="w-3.5 h-3.5" />
          </div>
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
              <span>Contactless Camera Vitals Extraction</span>
              <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.2 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                rPPG Optical
              </span>
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="flex items-center gap-1 text-slate-700 bg-white px-2 py-0.5 rounded-md border border-slate-200 font-mono text-[10px] shadow-2xs">
            <CheckCircle className="w-3 h-3 text-emerald-600" />
            <span>Confidence: {(vitals.confidence * 100).toFixed(0)}%</span>
          </span>
          <span className="text-[10px] text-slate-400 font-medium">
            {vitals.extractionDurationSec}s Scan
          </span>
        </div>
      </div>

      {/* 3 Compact Vital Metric Cards */}
      <div className="p-3">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
          {/* 1. Heart Rate Card */}
          <div className="bg-rose-50/40 rounded-xl p-2.5 px-3 border border-rose-100/90 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-semibold text-rose-800 uppercase tracking-wide">
                  Heart Rate (rPPG)
                </span>
              </div>
              <div className="mt-0.5 flex items-baseline gap-1.5">
                <span className="text-2xl font-black text-slate-900 tracking-tight">
                  {vitals.heartRateBpm}
                </span>
                <span className="text-[11px] font-semibold text-slate-500">BPM</span>
              </div>
              <div className="text-[10px] text-emerald-700 flex items-center gap-1 font-medium mt-0.5">
                <CheckCircle className="w-2.5 h-2.5 text-emerald-600 shrink-0" />
                <span className="truncate">Normal Sinus Rhythm (60-100)</span>
              </div>
            </div>

            <div className="w-9 h-9 rounded-xl bg-rose-100/80 text-rose-600 flex items-center justify-center shrink-0">
              <Heart className="w-4 h-4 fill-rose-500" />
            </div>
          </div>

          {/* 2. Respiratory Rate Card */}
          <div className="bg-sky-50/40 rounded-xl p-2.5 px-3 border border-sky-100/90 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-semibold text-sky-800 uppercase tracking-wide">
                  Resp Rate
                </span>
              </div>
              <div className="mt-0.5 flex items-baseline gap-1.5">
                <span className="text-2xl font-black text-slate-900 tracking-tight">
                  {vitals.respiratoryRateBpm}
                </span>
                <span className="text-[11px] font-semibold text-slate-500">breaths/min</span>
              </div>
              <div className="text-[10px] text-emerald-700 flex items-center gap-1 font-medium mt-0.5">
                <CheckCircle className="w-2.5 h-2.5 text-emerald-600 shrink-0" />
                <span className="truncate">Eupnea / Normal (12-20)</span>
              </div>
            </div>

            <div className="w-9 h-9 rounded-xl bg-sky-100/80 text-sky-600 flex items-center justify-center shrink-0">
              <Wind className="w-4 h-4" />
            </div>
          </div>

          {/* 3. Estimated SpO2 Card */}
          <div className="bg-teal-50/40 rounded-xl p-2.5 px-3 border border-teal-100/90 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-semibold text-teal-800 uppercase tracking-wide">
                  Est. Oxygen (SpO₂)
                </span>
              </div>
              <div className="mt-0.5 flex items-baseline gap-1.5">
                <span className="text-2xl font-black text-slate-900 tracking-tight">
                  {vitals.spo2Estimate || 98}%
                </span>
                <span className="text-[11px] font-semibold text-slate-500">O₂ saturation</span>
              </div>
              <div className="text-[10px] text-emerald-700 flex items-center gap-1 font-medium mt-0.5">
                <CheckCircle className="w-2.5 h-2.5 text-emerald-600 shrink-0" />
                <span className="truncate">Optimal Oxygenation</span>
              </div>
            </div>

            <div className="w-9 h-9 rounded-xl bg-teal-100/80 text-teal-600 flex items-center justify-center shrink-0">
              <Activity className="w-4 h-4" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
