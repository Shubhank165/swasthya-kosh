/**
 * Whether this screen is still live — 3/3 §7.
 *
 * "Show connection state honestly; if the socket is down, say so rather than
 * displaying a list that has quietly stopped updating." A worklist that looks
 * current and is twenty minutes old is the specific failure worth a permanent
 * pixel on this screen.
 */
import { useT, type StringKey } from '../i18n';
import type { ConnectionStatus } from '../lib/realtime';

const COPY: Record<ConnectionStatus, { key: StringKey; className: string; glyph: string }> = {
  live: {
    key: 'connection.live',
    glyph: '●',
    className: 'text-verified',
  },
  connecting: {
    key: 'connection.connecting',
    glyph: '◌',
    className: 'text-ink-muted',
  },
  reconnecting: {
    // Deliberately alarming wording in both languages. "Reconnecting" alone
    // reads as fine, and the list behind it is not.
    key: 'connection.reconnecting',
    glyph: '▲',
    className: 'text-uncertain',
  },
  offline: {
    key: 'connection.offline',
    glyph: '▲',
    className: 'text-urgent',
  },
};

export function ConnectionState({ status }: { status: ConnectionStatus }) {
  const t = useT();
  const copy = COPY[status];
  return (
    <span
      role="status"
      data-testid="connection-state"
      data-status={status}
      className={`inline-flex items-center gap-1.5 text-xs font-medium ${copy.className}`}
    >
      <span aria-hidden="true">{copy.glyph}</span>
      {t(copy.key)}
    </span>
  );
}
