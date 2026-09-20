/// The live queue, and the intake behind each row.
///
/// Plain `fetch` in an effect rather than a query library. The dashboard needs
/// two endpoints and one refresh interval; a cache layer would be more code
/// than it replaces, and this branch is already carrying a dependency tree that
/// nobody has needed to audit.
///
/// **A failed refresh keeps the last good queue on screen.** A physician
/// mid-consultation should not lose the record they are reading because the
/// venue wifi dropped for four seconds. The error is surfaced beside the data,
/// not instead of it, so the screen can say it is stale without going blank.

import { useCallback, useEffect, useRef, useState } from 'react';

import type { PatientQueueItem } from '../types';
import { api, DEFAULT_IDENTITY, type Identity } from './client';
import { toQueueItem } from './adapt';

const REFRESH_MS = 15_000;

export interface QueueState {
  patients: PatientQueueItem[];
  loading: boolean;
  /** Set when the most recent attempt failed. `patients` may still be good. */
  error: string | null;
  lastUpdated: Date | null;
  refresh: () => void;
}

export function useQueue(identity: Identity = DEFAULT_IDENTITY): QueueState {
  const [patients, setPatients] = useState<PatientQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [tick, setTick] = useState(0);
  const mounted = useRef(true);

  const refresh = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    (async () => {
      try {
        const worklist = await api.worklist(identity, controller.signal);
        // One detail call per row. The queue is an OPD session, not a
        // dataset — tens of rows, not thousands — and a row without its
        // intake cannot render a complaint, a severity or a vital.
        const rows = await Promise.all(
          worklist.entries.map(async (entry, index) => {
            try {
              const intake = await api.intake(entry.intake_id, identity, controller.signal);
              return toQueueItem(entry, intake, index);
            } catch {
              // One unreadable intake must not empty the whole queue.
              return null;
            }
          }),
        );
        if (!mounted.current) return;
        setPatients(rows.filter((row): row is PatientQueueItem => row !== null));
        setError(null);
        setLastUpdated(new Date());
      } catch (cause) {
        if (controller.signal.aborted || !mounted.current) return;
        setError(cause instanceof Error ? cause.message : 'the queue could not be loaded');
      } finally {
        if (mounted.current) setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [identity, tick]);

  useEffect(() => {
    const timer = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  return { patients, loading, error, lastUpdated, refresh };
}
