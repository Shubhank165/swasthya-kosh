import React, { useState } from 'react';
import { 
  Code, 
  Copy, 
  Check, 
  ArrowLeftRight, 
  FileText, 
  Sparkles,
  Info,
  Search
} from 'lucide-react';
import { IntakeData } from '../types';
import { KIOSK_DATA, APP_DATA } from '../data/patientIntakes';

interface JsonDiffViewerProps {
  currentData: IntakeData;
  onLoadCustomJson?: (json: IntakeData) => void;
}

export const JsonDiffViewer: React.FC<JsonDiffViewerProps> = ({ currentData }) => {
  const [viewMode, setViewMode] = useState<'diff_table' | 'active_json' | 'side_by_side'>('diff_table');
  const [copied, setCopied] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const diffRows = [
    {
      parameter: 'kiosk_id',
      app: 'null',
      kiosk: '"jetson-opd-1"',
      description: 'Identifies the physical NVIDIA Jetson terminal at the hospital OPD'
    },
    {
      parameter: 'engine_version',
      app: 'null',
      kiosk: '"medikiosk-0.1.0"',
      description: 'Local edge compute triage engine version on the kiosk hardware'
    },
    {
      parameter: 'extra top-level',
      app: 'source: "app", app_version: "1.0.0"',
      kiosk: '— (omitted / default kiosk telemetry)',
      description: 'Mobile app provenance tagging and bundle version'
    },
    {
      parameter: 'patient_ref.type',
      app: 'phone (peppered HMAC hash)',
      kiosk: 'hospital_id / guest',
      description: 'Privacy-preserving HMAC phone token vs walk-in guest token'
    },
    {
      parameter: 'turns[].transcript',
      app: 'null (tapped selection on touch screen)',
      kiosk: '"पेट में दर्द" (real speech audio)',
      description: 'Speech recognition transcript from patient voice vs touch UI taps'
    },
    {
      parameter: 'turns[].asr_confidence',
      app: 'null (deterministic touch tap)',
      kiosk: '0.93 - 0.99',
      description: 'Acoustic model confidence score for speech recognition'
    },
    {
      parameter: 'turns[].rms',
      app: 'null',
      kiosk: '508 (microphone RMS amplitude level)',
      description: 'Audio capture level metric preserved from hardware kiosk mic'
    },
    {
      parameter: 'question_id style',
      app: 'fixed.timeline, digestive.acidity (dotted)',
      kiosk: 'ask_complaint, ask_vomiting (bare)',
      description: 'Modular domain namespacing in app vs direct conversational prompts in kiosk'
    },
    {
      parameter: 'field ids',
      app: 'general.age, fever.chills (hierarchical)',
      kiosk: 'age, chief_complaint (flat / bare)',
      description: 'Schema evolution: App uses deep ontologies; kiosk uses direct clinical tokens'
    },
    {
      parameter: 'language_locked_at_turn',
      app: 'null (selected explicitly on onboarding)',
      kiosk: '2 (detected automatically from spoken language)',
      description: 'Audio speech language detection dynamically locks dialect'
    },
    {
      parameter: 'facts produced',
      app: '92 (37 answered + 50 not_applicable + 5 unresolved)',
      kiosk: '14 total facts',
      description: 'Mobile app comprehensive survey vs kiosk rapid 2-minute emergency triage'
    }
  ];

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(currentData, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filteredDiffs = diffRows.filter(r => 
    r.parameter.toLowerCase().includes(searchTerm.toLowerCase()) ||
    r.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 bg-slate-50/80 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs">
            <Code className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <span>Schema & Architecture Diff: App vs MediKiosk</span>
              <span className="text-[10px] font-mono font-bold bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full border border-indigo-200">
                v0.2 Spec
              </span>
            </h3>
            <p className="text-[11px] text-slate-500">
              Comparative analysis of JSON payloads produced by the Android/iOS app vs Jetson Kiosk
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center bg-slate-100 p-1 rounded-lg text-xs">
            <button
              type="button"
              onClick={() => setViewMode('diff_table')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === 'diff_table'
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Differential Matrix
            </button>

            <button
              type="button"
              onClick={() => setViewMode('side_by_side')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === 'side_by_side'
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Side-by-Side Payload
            </button>

            <button
              type="button"
              onClick={() => setViewMode('active_json')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                viewMode === 'active_json'
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Active Raw JSON
            </button>
          </div>

          <button
            type="button"
            onClick={handleCopyJson}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 transition-colors shadow-2xs"
            title="Copy active JSON to clipboard"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-slate-500" />}
            <span>{copied ? 'Copied' : 'Copy JSON'}</span>
          </button>
        </div>
      </div>

      <div className="p-5">
        {viewMode === 'diff_table' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div className="relative flex-1 max-w-sm">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Filter parameters..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg bg-white"
                />
              </div>

              <span className="text-xs text-slate-500">
                Displaying <strong>{filteredDiffs.length}</strong> architectural divergence points
              </span>
            </div>

            <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
              <table className="min-w-full text-xs divide-y divide-slate-200">
                <thead className="bg-slate-50 text-slate-700 font-semibold">
                  <tr>
                    <th className="py-2.5 px-3.5 text-left w-1/4">Parameter / Feature</th>
                    <th className="py-2.5 px-3.5 text-left w-1/4 bg-indigo-50/40 text-indigo-900">
                      Mobile App Payload
                    </th>
                    <th className="py-2.5 px-3.5 text-left w-1/4 bg-teal-50/40 text-teal-900">
                      Jetson Kiosk Payload
                    </th>
                    <th className="py-2.5 px-3.5 text-left">Clinical & Architectural Note</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {filteredDiffs.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/60 transition-colors">
                      <td className="py-2.5 px-3.5 font-mono font-semibold text-slate-900">
                        {row.parameter}
                      </td>
                      <td className="py-2.5 px-3.5 font-mono text-indigo-950 bg-indigo-50/15">
                        {row.app}
                      </td>
                      <td className="py-2.5 px-3.5 font-mono text-teal-950 bg-teal-50/15 font-semibold">
                        {row.kiosk}
                      </td>
                      <td className="py-2.5 px-3.5 text-slate-600 text-[11px] leading-relaxed">
                        {row.description}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {viewMode === 'side_by_side' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-100">
                <span className="text-xs font-bold text-teal-800">
                  Jetson Kiosk JSON (14 Facts)
                </span>
                <span className="text-[10px] font-mono bg-teal-50 text-teal-700 px-2 py-0.5 rounded">
                  intake_id: 82d32c07...
                </span>
              </div>
              <pre className="bg-slate-900 text-teal-300 p-3.5 rounded-xl font-mono text-[11px] h-96 overflow-auto leading-relaxed">
                {JSON.stringify(KIOSK_DATA, null, 2)}
              </pre>
            </div>

            <div>
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-100">
                <span className="text-xs font-bold text-indigo-800">
                  Mobile App JSON (92 Facts)
                </span>
                <span className="text-[10px] font-mono bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded">
                  intake_id: 72a5a663...
                </span>
              </div>
              <pre className="bg-slate-900 text-indigo-300 p-3.5 rounded-xl font-mono text-[11px] h-96 overflow-auto leading-relaxed">
                {JSON.stringify(APP_DATA, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {viewMode === 'active_json' && (
          <div>
            <div className="flex items-center justify-between text-xs text-slate-500 mb-2">
              <span>Active Payload in Memory ({Object.keys(currentData.fields).length} registered fields)</span>
              <span className="font-mono">schema_version: {currentData.schema_version}</span>
            </div>
            <pre className="bg-slate-900 text-emerald-400 p-4 rounded-xl font-mono text-xs max-h-[480px] overflow-auto leading-relaxed">
              {JSON.stringify(currentData, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
