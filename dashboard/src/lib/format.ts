/** Small, dull formatting helpers. Nothing here decides anything clinical. */

/** A timestamp as the hospital's staff read it: 24-hour, local. */
export function timeOfDay(iso: string | null | undefined): string {
  if (!iso) return '—';
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return '—';
  return when.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
}

export function dateAndTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return '—';
  return when.toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function isoDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return String(iso);
  return when.toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

/** `known_diabetes` -> `known diabetes`. Used only where no label exists. */
export function humanise(id: string): string {
  return id.replace(/_/g, ' ');
}
