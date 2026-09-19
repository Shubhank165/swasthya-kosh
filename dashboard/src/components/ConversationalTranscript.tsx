import React, { useState } from 'react';
import { 
  MessageSquare, 
  Mic, 
  Volume2, 
  CheckCircle2, 
  AlertCircle, 
  Filter, 
  Radio, 
  Sparkles,
  Search
} from 'lucide-react';
import { IntakeData, Turn } from '../types';

interface ConversationalTranscriptProps {
  currentData: IntakeData;
}

export const ConversationalTranscript: React.FC<ConversationalTranscriptProps> = ({ currentData }) => {
  const [filterType, setFilterType] = useState<'all' | 'resolved' | 'unresolved'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [playingTurnId, setPlayingTurnId] = useState<number | null>(null);

  const turns = currentData.turns || [];
  const isKiosk = currentData.kiosk_id !== null;

  // Filter turns
  const filteredTurns = turns.filter((turn) => {
    if (filterType === 'resolved' && !turn.resolved) return false;
    if (filterType === 'unresolved' && turn.resolved) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchQId = turn.question_id.toLowerCase().includes(q);
      const matchField = turn.bound_field.toLowerCase().includes(q);
      const matchTranscript = turn.transcript ? turn.transcript.toLowerCase().includes(q) : false;
      return matchQId || matchField || matchTranscript;
    }
    return true;
  });

  const handleSimulateAudioPlay = (turnId: number) => {
    setPlayingTurnId(turnId);
    setTimeout(() => {
      setPlayingTurnId((current) => (current === turnId ? null : current));
    }, 2500);
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden">
      {/* Card Header */}
      <div className="px-5 py-3.5 bg-slate-50/80 border-b border-slate-100 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-teal-100 text-teal-800 flex items-center justify-center font-bold text-xs">
            <MessageSquare className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <span>Conversational Agent Turn-by-Turn Triage</span>
              <span className="text-[10px] font-bold bg-teal-50 text-teal-700 px-2 py-0.5 rounded-full border border-teal-200">
                {isKiosk ? 'Voice ASR (Spoken)' : 'Mobile Tapped Input'}
              </span>
            </h3>
            <p className="text-[11px] text-slate-500">
              Interactive audit trail of dialogue turns between patient and MediKiosk agent
            </p>
          </div>
        </div>

        {/* Filter Controls */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search turn..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 pr-2.5 py-1 text-xs border border-slate-200 rounded-lg bg-white focus:outline-hidden focus:ring-1 focus:ring-teal-500 w-32 sm:w-40"
            />
          </div>

          <div className="flex items-center bg-slate-100 p-1 rounded-lg text-xs">
            <button
              type="button"
              onClick={() => setFilterType('all')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                filterType === 'all'
                  ? 'bg-white text-slate-900 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              All ({turns.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterType('resolved')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                filterType === 'resolved'
                  ? 'bg-white text-emerald-700 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Resolved ({turns.filter(t => t.resolved).length})
            </button>
            <button
              type="button"
              onClick={() => setFilterType('unresolved')}
              className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                filterType === 'unresolved'
                  ? 'bg-white text-amber-700 shadow-2xs font-semibold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Unresolved ({turns.filter(t => !t.resolved).length})
            </button>
          </div>
        </div>
      </div>

      {/* Unresolved Attention Alert if any */}
      {turns.filter(t => !t.resolved).length > 0 && (
        <div className="mx-5 mt-4 p-3 rounded-xl bg-amber-50/70 border border-amber-200/70 flex items-center justify-between text-xs text-amber-900">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              <strong>Doctor Attention:</strong> {turns.filter(t => !t.resolved).length} questions could not be resolved during patient triage (e.g. alcohol, surgery history, relieving factors).
            </span>
          </div>
          <button
            type="button"
            onClick={() => setFilterType('unresolved')}
            className="text-[11px] underline font-semibold text-amber-950 hover:text-amber-700"
          >
            Review Unresolved
          </button>
        </div>
      )}

      {/* Turn list */}
      <div className="p-5 max-h-[460px] overflow-y-auto space-y-3">
        {filteredTurns.length === 0 ? (
          <div className="text-center py-8 text-xs text-slate-400">
            No dialogue turns match the active filter.
          </div>
        ) : (
          filteredTurns.map((turn) => {
            const isPlaying = playingTurnId === turn.turn_id;
            const boundFieldData = currentData.fields[turn.bound_field];
            const originalText = boundFieldData?.original_text || turn.transcript;

            return (
              <div
                key={turn.turn_id}
                className={`p-3.5 rounded-xl border transition-all ${
                  turn.resolved
                    ? 'bg-slate-50/60 border-slate-200/80 hover:bg-slate-50'
                    : 'bg-amber-50/40 border-amber-200/80'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <span className="w-6 h-6 rounded-md bg-slate-200/80 text-slate-700 font-mono text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
                      {turn.turn_id}
                    </span>

                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-bold text-slate-900 font-mono">
                          {turn.question_id}
                        </span>
                        <span className="text-slate-300">→</span>
                        <code className="text-[11px] bg-slate-200/60 text-slate-700 px-1.5 py-0.2 rounded font-mono">
                          {turn.bound_field}
                        </code>

                        {turn.resolved ? (
                          <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-100/70 px-2 py-0.2 rounded-full flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Resolved
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold text-amber-800 bg-amber-100 px-2 py-0.2 rounded-full flex items-center gap-1">
                            <AlertCircle className="w-3 h-3 text-amber-600" /> Unresolved (Doctor Review)
                          </span>
                        )}
                      </div>

                      {/* Patient Transcript / Answer */}
                      <div className="mt-2 text-xs">
                        {turn.transcript || originalText ? (
                          <div className="flex items-start gap-2">
                            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide shrink-0 mt-0.5">
                              Patient:
                            </span>
                            <div className="bg-white px-3 py-1.5 rounded-lg border border-slate-200/80 text-slate-800 font-medium shadow-2xs">
                              "{turn.transcript || originalText}"
                            </div>
                          </div>
                        ) : (
                          <span className="text-slate-400 italic text-[11px]">
                            {turn.resolved ? 'UI selection registered via screen' : 'Skipped or unconfirmed by patient'}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Kiosk Voice Waveform & ASR confidence metrics */}
                  {isKiosk && turn.transcript && (
                    <div className="flex items-center gap-2 shrink-0">
                      <div className="text-right hidden sm:block">
                        <div className="text-[10px] font-mono text-slate-500">
                          ASR Conf: <span className="font-bold text-teal-700">{((turn.asr_confidence || 0.94) * 100).toFixed(0)}%</span>
                        </div>
                        <div className="text-[9px] font-mono text-slate-400">
                          RMS Mic: {turn.rms || 508}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleSimulateAudioPlay(turn.turn_id)}
                        className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
                          isPlaying
                            ? 'bg-teal-600 text-white animate-pulse'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                        }`}
                        title="Listen to audio recording"
                      >
                        <Volume2 className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
