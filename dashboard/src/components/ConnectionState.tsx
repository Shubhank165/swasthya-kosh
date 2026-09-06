/**
 * Whether this screen is still live — 3/3 §7.
 *
 * "Show connection state honestly; if the socket is down, say so rather than
 * displaying a list that has quietly stopped updating." A worklist that looks
 * current and is twenty minutes old is the specific failure worth a permanent
 * pixel on this screen.
 */
import type { ConnectionStatus } from '../lib/realtime';

const COPY: Record<ConnectionStatus, { text: string; className: string; glyph: string }> = {
  live: {
    text: 'Live',
    glyph: '●',
    className: 'text-verified',
  },
  connecting: {
    text: 'Connecting…',
    glyph: '◌',
    className: 'text-ink-muted',
  },
  reconnecting: {
    // Deliberately alarming wording. "Reconnecting" alone reads as fine.
    text: 'Not updating — reconnecting',
    glyph: '▲',
    className: 'text-uncertain',
  },
  offline: {
    text: 'Not updating — no connection',
    glyph: '▲',
    className: 'text-urgent',
  },
};

export function ConnectionState({ status }: { status: ConnectionStatus }) {
  const copy = COPY[status];
  return (
    <span
      role="status"
      data-testid="connection-state"
      data-status={status}
      className={`inline-flex items-center gap-1.5 text-xs font-medium ${copy.className}`}
    >
      <span aria-hidden="true">{copy.glyph}</span>
      {copy.text}
    </span>
  );
}
