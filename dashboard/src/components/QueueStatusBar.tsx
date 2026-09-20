/// Whether what is on screen is current, and what to do when it is not.
///
/// The queue refreshes every fifteen seconds and a failed refresh keeps the
/// last good rows rather than blanking them — which is right, and is also
/// exactly how a physician ends up reading a stale queue without knowing it.
/// So the state is stated rather than implied: live, or stale since a named
/// time, with the reason and a way to retry.

import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  count: number;
  onRefresh: () => void;
}

export function QueueStatusBar({ loading, error, lastUpdated, count, onRefresh }: Props) {
  const when = lastUpdated
    ? lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null;

  return (
    <div
      role="status"
      className={`px-6 py-2 text-xs flex items-center gap-3 border-b ${
        error ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-white border-slate-200 text-slate-600'
      }`}
    >
      {error ? (
        <AlertTriangle className="w-4 h-4 shrink-0" />
      ) : (
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${loading ? 'bg-slate-400' : 'bg-emerald-500'}`}
        />
      )}

      <span className="font-medium">
        {error
          ? 'Not updating — showing the last queue that loaded'
          : loading
            ? 'Loading the OPD queue…'
            : `Live — ${count} patient${count === 1 ? '' : 's'}`}
      </span>

      {when && <span className="text-slate-400">last updated {when}</span>}
      {error && <span className="truncate text-amber-700/80">{error}</span>}

      <button
        onClick={onRefresh}
        className="ml-auto inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-slate-300 bg-white hover:bg-slate-50 text-slate-700"
      >
        <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        Refresh
      </button>
    </div>
  );
}
