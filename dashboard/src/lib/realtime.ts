/**
 * The worklist socket — 3/3 §7.
 *
 * Two decisions, and both are about what happens when the connection is not
 * perfect, which on a hospital LAN is most of the time.
 *
 * **On reconnect it refetches rather than replays.** A gap in a message stream
 * is invisible; a dashboard that stitched itself back together from whatever
 * arrived after the gap would show a clinical state that never existed and give
 * no sign of it. Refetching costs a request and is correct.
 *
 * **Connection state is displayed, not hidden.** A socket that has quietly
 * died leaves a list that looks live and is not, and a physician working down a
 * stale worklist is the failure this whole screen exists to prevent. `status`
 * is returned so the UI can say so out loud.
 *
 * The frames themselves carry no clinical text — the backend's `Event` model
 * forbids it structurally — so nothing here needs to redact anything, and
 * nothing here reads a payload for content.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

/** Event names from `app/events/schemas.py::EventName`. */
export const WORKLIST_EVENTS = [
  'intake.received',
  'intake.needs_review',
  'intake.seen',
  'intake.redflag.received',
  'intake.redflag.acknowledged',
  'intake.contradiction.detected',
  'document.processed',
  'document.low_confidence',
  'document.rejected',
  'report.ready',
  'report.physician_verified',
] as const;

export type WorklistEventName = (typeof WORKLIST_EVENTS)[number];

export interface RealtimeFrame {
  event: string;
  occurred_at?: string;
  department_code?: string;
  intake_id?: string;
  alert_id?: string;
  document_id?: string;
  actor_id?: string;
  payload?: Record<string, unknown>;
}

export type ConnectionStatus = 'connecting' | 'live' | 'reconnecting' | 'offline';

/** Backoff in ms, capped. A hospital LAN drops for seconds, not milliseconds. */
const BACKOFF_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

export interface RealtimeOptions {
  department: string | null;
  /**
   * Called when the socket delivers something that changes the worklist, and
   * again after every successful reconnect. The caller refetches; this hook
   * deliberately does not know what a worklist is.
   */
  onChange: () => void;
  /** Off in tests and wherever a socket would be noise. */
  enabled?: boolean;
  /** Injectable for tests. Defaults to the global. */
  socketFactory?: (url: string) => WebSocket;
}

export function worklistSocketUrl(department: string | null): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const query = department ? `?department=${encodeURIComponent(department)}` : '';
  return `${protocol}//${window.location.host}/ws/worklist${query}`;
}

export function useWorklistSocket({
  department,
  onChange,
  enabled = true,
  socketFactory,
}: RealtimeOptions) {
  const [status, setStatus] = useState<ConnectionStatus>(
    enabled ? 'connecting' : 'offline',
  );
  const [lastEvent, setLastEvent] = useState<RealtimeFrame | null>(null);

  // Held in a ref so a changing callback identity does not tear the socket
  // down and rebuild it on every render — which, with backoff, is a reconnect
  // storm that looks like a flaky network.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const attempt = useRef(0);
  const socketRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUs = useRef(false);

  const connect = useCallback(() => {
    if (!enabled) return;
    const factory = socketFactory ?? ((url: string) => new WebSocket(url));
    const socket = factory(worklistSocketUrl(department));
    socketRef.current = socket;

    socket.onopen = () => {
      const reconnected = attempt.current > 0;
      attempt.current = 0;
      setStatus('live');
      // Refetch on every reconnect, including the first. Whatever happened
      // while we were not listening is not recoverable from the stream.
      if (reconnected) onChangeRef.current();
    };

    socket.onmessage = (message: MessageEvent<string>) => {
      let frame: RealtimeFrame;
      try {
        frame = JSON.parse(message.data) as RealtimeFrame;
      } catch {
        // A frame we cannot parse is a frame we cannot act on. Nothing is
        // logged: the parse failed, so we do not know that the payload was
        // free of clinical text (§1 rule 7).
        return;
      }
      if (frame.event === 'heartbeat' || frame.event === 'subscribed') return;
      setLastEvent(frame);
      if ((WORKLIST_EVENTS as readonly string[]).includes(frame.event)) {
        onChangeRef.current();
      }
    };

    socket.onclose = () => {
      socketRef.current = null;
      if (closedByUs.current) return;
      setStatus('reconnecting');
      const delay = BACKOFF_MS[Math.min(attempt.current, BACKOFF_MS.length - 1)]!;
      attempt.current += 1;
      timerRef.current = setTimeout(connect, delay);
    };

    socket.onerror = () => {
      // `onclose` always follows, and it owns the retry. Handling both would
      // schedule two reconnects for one failure.
    };
  }, [department, enabled, socketFactory]);

  useEffect(() => {
    closedByUs.current = false;
    if (!enabled) {
      setStatus('offline');
      return;
    }
    setStatus('connecting');
    connect();
    return () => {
      closedByUs.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [connect, enabled]);

  return { status, lastEvent };
}
