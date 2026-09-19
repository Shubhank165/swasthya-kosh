import React, { useState } from 'react';
import { 
  Building2, 
  Search, 
  Users, 
  Clock, 
  ShieldCheck, 
  Activity, 
  Monitor, 
  Smartphone, 
  ArrowRight, 
  CheckCircle2, 
  AlertCircle, 
  ChevronRight,
  Filter,
  Stethoscope,
  Sparkles
} from 'lucide-react';
import { PatientQueueItem } from '../types';

interface OpdPatientQueueViewProps {
  queue: PatientQueueItem[];
  onSelectPatient: (patient: PatientQueueItem) => void;
}

export const OpdPatientQueueView: React.FC<OpdPatientQueueViewProps> = ({
  queue,
  onSelectPatient
}) => {
  const [filterStatus, setFilterStatus] = useState<'all' | 'waiting' | 'in_consultation' | 'completed'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredQueue = queue.filter((patient) => {
    if (filterStatus !== 'all' && patient.queueStatus !== filterStatus) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = patient.name.toLowerCase().includes(q);
      const matchToken = patient.tokenNumber.toLowerCase().includes(q);
      const matchAbha = patient.abhaNumber.toLowerCase().includes(q);
      const matchComplaint = patient.chiefComplaint.toLowerCase().includes(q);
      return matchName || matchToken || matchAbha || matchComplaint;
    }
    return true;
  });

  const waitingCount = queue.filter(p => p.queueStatus === 'waiting').length;
  const inConsultCount = queue.filter(p => p.queueStatus === 'in_consultation').length;
  const completedCount = queue.filter(p => p.queueStatus === 'completed').length;

  return (
    <div className="min-h-screen bg-slate-100/70 text-slate-800 flex flex-col font-sans antialiased">
      {/* Top hospital & OPD header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-xl bg-teal-700 flex items-center justify-center text-white shadow-xs">
              <Building2 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="font-bold text-slate-900 text-lg leading-tight">
                  All India Institute of Ayurveda (AIIA), Delhi
                </h1>
                <span className="text-xs font-semibold bg-teal-50 text-teal-800 px-2.5 py-0.5 rounded-full border border-teal-200">
                  Kayachikitsa OPD
                </span>
              </div>
              <p className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                <span>Doctor Consultation Station #04</span>
                <span className="text-slate-300">•</span>
                <span className="text-teal-700 font-semibold">Dr. S. K. Sharma, MD (Ayu)</span>
                <span className="text-slate-300">•</span>
                <span className="flex items-center gap-1 text-emerald-600 font-medium">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  MediKiosk & Mobile Live Queue Connected
                </span>
              </p>
            </div>
          </div>

          {/* Quick Doctor Metrics */}
          <div className="flex items-center gap-2 bg-slate-50 p-1.5 rounded-xl border border-slate-200 text-xs">
            <div className="px-3 py-1 text-center">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">Waiting</span>
              <span className="text-sm font-bold text-amber-600 font-mono">{waitingCount}</span>
            </div>
            <div className="w-px h-6 bg-slate-200" />
            <div className="px-3 py-1 text-center">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">In Consult</span>
              <span className="text-sm font-bold text-teal-700 font-mono">{inConsultCount}</span>
            </div>
            <div className="w-px h-6 bg-slate-200" />
            <div className="px-3 py-1 text-center">
              <span className="text-[10px] uppercase font-bold text-slate-400 block">Total OPD</span>
              <span className="text-sm font-bold text-slate-800 font-mono">{queue.length}</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Welcome & Action Banner */}
        <div className="bg-gradient-to-r from-teal-50/90 via-emerald-50/40 to-slate-50 border border-teal-200/80 rounded-2xl p-6 text-slate-800 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-teal-800 text-xs font-semibold uppercase tracking-wider mb-1">
              <Users className="w-4 h-4 text-teal-600" />
              <span>Outpatient Department (OPD) Triage Queue</span>
            </div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900">
              Pre-Consultation Patient Registry
            </h2>
          </div>

          <div className="shrink-0">
            {waitingCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  const nextPatient = queue.find(p => p.queueStatus === 'waiting') || queue[0];
                  if (nextPatient) onSelectPatient(nextPatient);
                }}
                className="px-4 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-700 text-white font-bold text-xs flex items-center gap-2 transition-all shadow-xs"
              >
                <Stethoscope className="w-4 h-4" />
                <span>Call Next Patient ({queue.find(p => p.queueStatus === 'waiting')?.tokenNumber || '#OPD-041'})</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Search & Filter Toolbar */}
        <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-2xs flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          {/* Search */}
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by patient name, token #, ABHA, or complaint..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 text-xs border border-slate-200 rounded-xl bg-slate-50/50 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-teal-500 transition-all"
            />
          </div>

          {/* Filter Status Buttons */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl text-xs gap-1 overflow-x-auto">
            <button
              type="button"
              onClick={() => setFilterStatus('all')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all whitespace-nowrap ${
                filterStatus === 'all'
                  ? 'bg-white text-slate-900 shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              All Patients ({queue.length})
            </button>

            <button
              type="button"
              onClick={() => setFilterStatus('waiting')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all whitespace-nowrap ${
                filterStatus === 'waiting'
                  ? 'bg-white text-amber-700 shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Waiting ({waitingCount})
            </button>

            <button
              type="button"
              onClick={() => setFilterStatus('in_consultation')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all whitespace-nowrap ${
                filterStatus === 'in_consultation'
                  ? 'bg-white text-teal-800 shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              In Consultation ({inConsultCount})
            </button>

            <button
              type="button"
              onClick={() => setFilterStatus('completed')}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all whitespace-nowrap ${
                filterStatus === 'completed'
                  ? 'bg-white text-emerald-800 shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Completed ({completedCount})
            </button>
          </div>
        </div>

        {/* Patient Queue Cards List */}
        <div className="space-y-3.5">
          {filteredQueue.length === 0 ? (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center text-slate-400">
              <Users className="w-10 h-10 mx-auto text-slate-300 mb-2" />
              <p className="text-sm font-semibold text-slate-600">No patients match the search or filter criteria.</p>
              <p className="text-xs text-slate-400 mt-1">Try resetting the filter to 'All Patients'.</p>
            </div>
          ) : (
            filteredQueue.map((patient) => {
              const isUrgent = patient.severity >= 7;

              return (
                <div
                  key={patient.id}
                  onClick={() => onSelectPatient(patient)}
                  className={`bg-white rounded-2xl border transition-all duration-150 p-5 hover:border-teal-400 hover:shadow-md cursor-pointer relative overflow-hidden group ${
                    patient.queueStatus === 'in_consultation'
                      ? 'border-teal-300 ring-1 ring-teal-400/30 bg-teal-50/10'
                      : 'border-slate-200/90'
                  }`}
                >
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                    {/* Left: Token, Demographics, ABHA */}
                    <div className="flex items-start gap-4">
                      {/* Token Box */}
                      <div className="flex flex-col items-center justify-center w-20 h-20 rounded-2xl bg-teal-50/80 border border-teal-200/90 text-teal-950 shrink-0 shadow-2xs group-hover:bg-teal-100/70 group-hover:border-teal-300 transition-colors">
                        <span className="text-[10px] text-teal-700 font-bold uppercase tracking-wider">TOKEN</span>
                        <span className="font-mono font-extrabold text-base tracking-tight text-teal-900">
                          {patient.tokenNumber}
                        </span>
                        <span className="text-[10px] text-slate-500 font-medium mt-0.5">{patient.arrivalTime}</span>
                      </div>

                      {/* Info */}
                      <div>
                        <div className="flex items-center gap-2.5 flex-wrap">
                          <h3 className="text-base font-bold text-slate-900 group-hover:text-teal-700 transition-colors">
                            {patient.name}
                          </h3>
                          <span className="text-xs text-slate-500 font-medium">
                            {patient.age} Y / {patient.gender}
                          </span>

                          {/* ABHA Badge */}
                          {patient.abhaVerified ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                              <ShieldCheck className="w-3 h-3 text-emerald-600" />
                              ABHA: {patient.abhaNumber}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-800 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
                              ABHA Pending
                            </span>
                          )}

                          {/* Source Origin Badge */}
                          {patient.source === 'kiosk' ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-teal-800 bg-teal-50 border border-teal-200 px-2 py-0.5 rounded-full">
                              <Monitor className="w-3 h-3 text-teal-600" />
                              MediKiosk ({patient.kioskId || 'jetson-opd-1'})
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-800 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
                              <Smartphone className="w-3 h-3 text-indigo-600" />
                              Mobile App Pre-Queue
                            </span>
                          )}
                        </div>

                        {/* Chief Complaint */}
                        <div className="mt-2 flex items-baseline gap-2">
                          <span className="text-xs font-bold text-slate-500 uppercase tracking-wide shrink-0">
                            Chief Complaint:
                          </span>
                          <span className="text-xs font-semibold text-slate-800">
                            {patient.chiefComplaint}
                          </span>
                        </div>

                        {/* Status & Severity */}
                        <div className="mt-2.5 flex items-center gap-3 flex-wrap">
                          <span
                            className={`inline-flex items-center gap-1 text-xs font-bold px-2.5 py-0.5 rounded-md ${
                              patient.queueStatus === 'in_consultation'
                                ? 'bg-teal-100 text-teal-900 border border-teal-300'
                                : patient.queueStatus === 'waiting'
                                ? 'bg-amber-100 text-amber-900 border border-amber-200'
                                : 'bg-emerald-100 text-emerald-900 border border-emerald-200'
                            }`}
                          >
                            {patient.queueStatus === 'in_consultation' && '🩺 In Consultation'}
                            {patient.queueStatus === 'waiting' && '⏳ Waiting in Queue'}
                            {patient.queueStatus === 'completed' && '✅ Completed'}
                          </span>

                          <span className="text-xs text-slate-500 flex items-center gap-1">
                            <span>Pain Severity:</span>
                            <span className={`font-bold font-mono ${isUrgent ? 'text-rose-600' : 'text-slate-800'}`}>
                              {patient.severity}/10
                            </span>
                            {isUrgent && (
                              <span className="text-[10px] font-bold text-rose-700 bg-rose-50 px-1.5 py-0.2 rounded border border-rose-200">
                                High
                              </span>
                            )}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Right: Camera Vitals Pill & Open Action */}
                    <div className="flex items-center gap-4 lg:self-center shrink-0 border-t lg:border-t-0 pt-3 lg:pt-0 border-slate-100">
                      {/* Vitals */}
                      <div className="bg-slate-50 border border-slate-200/90 rounded-xl px-3.5 py-2 flex items-center gap-4 font-mono text-xs">
                        <div className="text-center">
                          <span className="text-[9px] text-slate-400 uppercase tracking-wide block">Pulse</span>
                          <span className="font-bold text-slate-900">{patient.vitalsSummary.hr} <span className="text-[10px] text-slate-500 font-normal">BPM</span></span>
                        </div>
                        <div className="w-px h-5 bg-slate-200" />
                        <div className="text-center">
                          <span className="text-[9px] text-slate-400 uppercase tracking-wide block">Resp</span>
                          <span className="font-bold text-slate-900">{patient.vitalsSummary.rr} <span className="text-[10px] text-slate-500 font-normal">/min</span></span>
                        </div>
                        <div className="w-px h-5 bg-slate-200" />
                        <div className="text-center">
                          <span className="text-[9px] text-slate-400 uppercase tracking-wide block">SpO2</span>
                          <span className="font-bold text-slate-900">{patient.vitalsSummary.spo2}%</span>
                        </div>
                      </div>

                      {/* Open Consultation Button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectPatient(patient);
                        }}
                        className="px-4 py-2.5 rounded-xl bg-teal-600 hover:bg-teal-700 text-white font-bold text-xs flex items-center gap-1.5 transition-colors shadow-xs group-hover:bg-teal-700"
                      >
                        <span>{patient.queueStatus === 'in_consultation' ? 'Resume Portal' : 'Open Portal'}</span>
                        <ChevronRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 mt-10 py-4 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>
            MediKiosk Clinical Triage System • All India Institute of Ayurveda, New Delhi
          </span>
          <span className="text-[11px] text-slate-400 font-mono">
            OPD Server: jetson-cluster-delhi-01 • Active Queue: {queue.length}
          </span>
        </div>
      </footer>
    </div>
  );
};
