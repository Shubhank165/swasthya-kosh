import React, { useState } from 'react';
import { 
  Activity, 
  FileText, 
  MessageSquare, 
  FileSearch, 
  Sparkles, 
  ShieldCheck, 
  LayoutDashboard,
  ArrowRight,
  ArrowLeft,
  ChevronRight,
  Pill,
  Clock,
  Eye
} from 'lucide-react';
import { IntakeData, PatientQueueItem } from './types';
import { OPD_PATIENT_QUEUE } from './data/patientIntakes';
import { OpdPatientQueueView } from './components/OpdPatientQueueView';
import { Header } from './components/Header';
import { VitalsStation } from './components/VitalsStation';
import { ChiefComplaintCard } from './components/ChiefComplaintCard';
import { AyurvedicProfile } from './components/AyurvedicProfile';
import { OcrPrescriptionsLabs } from './components/OcrPrescriptionsLabs';
import { ConversationalTranscript } from './components/ConversationalTranscript';
import { AbhaDetailsModal } from './components/AbhaDetailsModal';
import { PrintableOpdSlip } from './components/PrintableOpdSlip';

type TabType = 'overview' | 'ayurveda' | 'complaints' | 'vitals' | 'ocr' | 'transcripts';

export default function App() {
  const [viewMode, setViewMode] = useState<'queue' | 'patient_portal'>('queue');
  const [patientQueue, setPatientQueue] = useState<PatientQueueItem[]>(OPD_PATIENT_QUEUE);
  const [selectedPatientId, setSelectedPatientId] = useState<string>('p-042');
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [showAbhaModal, setShowAbhaModal] = useState(false);
  const [showPrintModal, setShowPrintModal] = useState(false);

  // Active Patient Object
  const currentPatient = patientQueue.find(p => p.id === selectedPatientId) || patientQueue[0];
  const currentData: IntakeData = currentPatient.intakeData;

  // Next patient navigation
  const currentIndex = patientQueue.findIndex(p => p.id === selectedPatientId);
  const hasNextPatient = currentIndex >= 0 && currentIndex < patientQueue.length - 1;
  const nextPatient = hasNextPatient ? patientQueue[currentIndex + 1] : null;

  const handleSelectPatient = (patient: PatientQueueItem) => {
    setSelectedPatientId(patient.id);
    setViewMode('patient_portal');
    setActiveTab('overview');
  };

  const handleNextPatient = () => {
    if (hasNextPatient && nextPatient) {
      setSelectedPatientId(nextPatient.id);
      setActiveTab('overview');
    }
  };

  const handleStatusChange = (newStatus: string) => {
    setPatientQueue(prev =>
      prev.map(p => (p.id === currentPatient.id ? { ...p, queueStatus: newStatus as PatientQueueItem['queueStatus'] } : p))
    );
  };

  if (viewMode === 'queue') {
    return (
      <OpdPatientQueueView
        queue={patientQueue}
        onSelectPatient={handleSelectPatient}
      />
    );
  }

  const tabs: Array<{ id: TabType; label: string; icon: React.ReactNode; badge?: string; isEyeCatchy?: boolean }> = [
    { id: 'overview', label: 'Clinical Overview', icon: <LayoutDashboard className="w-4 h-4" /> },
    { 
      id: 'ayurveda', 
      label: 'Ayurvedic Info (Prakriti & Pariksha)', 
      icon: <Sparkles className="w-4 h-4 text-amber-500" />, 
      badge: String(currentData.fields.ayurveda_dosha_tendency?.value?.text || 'Pitta'),
      isEyeCatchy: true 
    },
    { id: 'complaints', label: 'Chief Complaint', icon: <FileText className="w-4 h-4" />, badge: `Severity ${currentData.fields['general.severity']?.value?.value ?? currentData.fields.severity?.value?.value ?? 7}/10` },
    { id: 'vitals', label: 'Contactless Vitals', icon: <Activity className="w-4 h-4" />, badge: `${currentData.cameraVitals?.heartRateBpm || 76} BPM` },
    { id: 'ocr', label: 'Scanned Records', icon: <FileSearch className="w-4 h-4" />, badge: 'Rx & Labs' },
    { id: 'transcripts', label: 'Voice Triage Dialogue', icon: <MessageSquare className="w-4 h-4" />, badge: `${currentData.turns.length} turns` },
  ];

  return (
    <div className="min-h-screen bg-slate-100/70 text-slate-800 flex flex-col font-sans antialiased">
      {/* Top Header & Patient Bar */}
      <Header
        currentData={currentData}
        patientToken={currentPatient.tokenNumber}
        onBackToQueue={() => setViewMode('queue')}
        onNextPatient={handleNextPatient}
        hasNextPatient={hasNextPatient}
        onPrint={() => setShowPrintModal(true)}
        onToggleAbhaModal={() => setShowAbhaModal(true)}
        statusText={currentPatient.queueStatus}
        onChangeStatusText={handleStatusChange}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-5">
        <div className="flex flex-col lg:flex-row gap-5 items-start">
          {/* Left Navigation Options Sidebar */}
          <aside className="w-full lg:w-64 shrink-0 lg:sticky lg:top-20 space-y-3">
            <div className="bg-white rounded-2xl border border-slate-200/90 p-2 shadow-2xs space-y-1">
              <div className="px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-100 mb-1 flex items-center justify-between">
                <span>Clinical Modules</span>
                <span className="text-[10px] font-mono text-slate-500 bg-slate-100 px-1.5 py-0.2 rounded">
                  JSON Intake
                </span>
              </div>

              {tabs.map((tab) => {
                const isActive = activeTab === tab.id;
                
                if (tab.isEyeCatchy) {
                  return (
                    <button
                      key={tab.id}
                      id={`tab-${tab.id}`}
                      type="button"
                      onClick={() => setActiveTab(tab.id)}
                      className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl text-xs font-bold transition-all shadow-xs ${
                        isActive
                          ? 'bg-gradient-to-r from-amber-500 via-orange-500 to-emerald-600 text-white ring-2 ring-amber-400/40'
                          : 'bg-amber-50 text-amber-900 hover:bg-amber-100 border border-amber-200/80'
                      }`}
                    >
                      <div className="flex items-center gap-2 truncate">
                        <Sparkles className={`w-4 h-4 shrink-0 ${isActive ? 'text-amber-200 animate-pulse' : 'text-amber-600'}`} />
                        <span className="truncate">{tab.label}</span>
                      </div>
                      {tab.badge && (
                        <span
                          className={`text-[10px] px-1.5 py-0.2 rounded-full font-semibold uppercase shrink-0 ${
                            isActive
                              ? 'bg-white/25 text-white'
                              : 'bg-amber-200/70 text-amber-900'
                          }`}
                        >
                          {tab.badge}
                        </span>
                      )}
                    </button>
                  );
                }

                return (
                  <button
                    key={tab.id}
                    id={`tab-${tab.id}`}
                    type="button"
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                      isActive
                        ? 'bg-teal-700 text-white shadow-xs'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 truncate">
                      <span className={isActive ? 'text-white' : 'text-slate-500'}>{tab.icon}</span>
                      <span className="truncate">{tab.label}</span>
                    </div>
                    {tab.badge && (
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-normal shrink-0 ${
                          isActive
                            ? 'bg-white/20 text-white'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {tab.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </aside>

          {/* Main Content Area */}
          <section className="flex-1 min-w-0 w-full space-y-5">
            {/* Tab Views */}
            {activeTab === 'overview' && (
              <div className="space-y-5">
                {/* Quick Doctor Triage Notification Bar */}
                <div className="bg-gradient-to-r from-teal-500/10 via-emerald-500/5 to-amber-500/10 border border-teal-200/70 rounded-2xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-teal-600 text-white flex items-center justify-center font-bold shrink-0 shadow-xs">
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">
                        Pre-Consultation Intake Ready • {currentPatient.tokenNumber} ({currentPatient.name})
                      </h3>
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5 shrink-0">
                    <button
                      id="btn-ayurvedic-info"
                      type="button"
                      onClick={() => setActiveTab('ayurveda')}
                      className="px-4 py-2 rounded-xl bg-gradient-to-r from-amber-500 via-orange-500 to-emerald-600 hover:from-amber-600 hover:to-emerald-700 text-white text-xs font-bold flex items-center gap-2 transition-all shadow-md hover:shadow-lg ring-2 ring-amber-400/40 ring-offset-2 ring-offset-white hover:-translate-y-0.5 active:translate-y-0 cursor-pointer"
                      title="Switch to Ayurvedic Clinical Assessment"
                    >
                      <Sparkles className="w-4 h-4 text-amber-200 fill-amber-200" />
                      <span>Ayurvedic Info</span>
                      <ArrowRight className="w-3.5 h-3.5 ml-0.5 text-white/90" />
                    </button>

                    {hasNextPatient && (
                      <button
                        type="button"
                        onClick={handleNextPatient}
                        className="px-3.5 py-2 rounded-xl bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-2xs"
                      >
                        <span>Next Patient ({nextPatient?.tokenNumber})</span>
                        <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
                      </button>
                    )}
                  </div>
                </div>

                {/* 1. Chief Complaint & Clinical Progression (Includes Vitals, Ongoing Meds & History) */}
                <ChiefComplaintCard currentData={currentData} />

                {/* 2. OCR Scanned Records & Diagnostic Labs */}
                <OcrPrescriptionsLabs currentData={currentData} />

                {/* 3. Ayurvedic Prakriti & Pariksha Assessment */}
                <AyurvedicProfile currentData={currentData} />
              </div>
            )}

            {/* Dedicated Tab: Ayurvedic Info (Prakriti & Pariksha) */}
            {activeTab === 'ayurveda' && (
              <div className="space-y-4">
                <AyurvedicProfile currentData={currentData} />
              </div>
            )}

            {/* Dedicated Tab: Chief Complaint */}
            {activeTab === 'complaints' && (
              <ChiefComplaintCard currentData={currentData} />
            )}

            {/* Dedicated Tab: Contactless Camera Vitals */}
            {activeTab === 'vitals' && (
              <div className="space-y-4">
                <VitalsStation currentData={currentData} />
                <div className="bg-white rounded-2xl border border-slate-200 p-5 text-xs text-slate-600">
                  <h4 className="font-bold text-slate-900 text-sm mb-2">
                    About Contactless Camera Vital Extraction in MediKiosk
                  </h4>
                  <p className="leading-relaxed">
                    The MediKiosk hardware terminal utilizes an NVIDIA Jetson platform equipped with a high-frame-rate Sony IMX sensor. It executes remote photoplethysmography (rPPG) by quantifying micro-chromatic shifts in reflected ambient light caused by facial capillary pulsations, accompanied by thoracic cage motion tracking for real-time breath rate extraction.
                  </p>
                </div>
              </div>
            )}

            {/* Dedicated Tab: OCR Scanned Records */}
            {activeTab === 'ocr' && (
              <OcrPrescriptionsLabs currentData={currentData} />
            )}

            {/* Dedicated Tab: Voice Triage Dialogue */}
            {activeTab === 'transcripts' && (
              <ConversationalTranscript currentData={currentData} />
            )}
          </section>
        </div>
      </main>

      {/* ABHA Modal */}
      {showAbhaModal && (
        <AbhaDetailsModal
          currentData={currentData}
          onClose={() => setShowAbhaModal(false)}
        />
      )}

      {/* Print OPD Slip Modal */}
      {showPrintModal && (
        <PrintableOpdSlip
          currentData={currentData}
          onClose={() => setShowPrintModal(false)}
        />
      )}

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 mt-10 py-4 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setViewMode('queue')}
              className="text-teal-700 font-semibold hover:underline flex items-center gap-1"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Patient Queue</span>
            </button>
            <span className="text-slate-300">•</span>
            <span>MediKiosk Clinical Doctor Dashboard • AIIA Delhi</span>
          </div>
          <span className="text-[11px] text-slate-400">
            Intake Source: <strong>{currentPatient.source === 'kiosk' ? `MediKiosk (${currentPatient.kioskId})` : 'Mobile App Pre-Queue'}</strong>
          </span>
        </div>
      </footer>
    </div>
  );
}
