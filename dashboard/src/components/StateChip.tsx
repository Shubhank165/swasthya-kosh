/** One qualifier, as a chip — 3/3 §4.2. Shape and label, never colour alone. */
import { STATE_STYLES, type FactState } from '../report/factState';

export function StateChip({ state }: { state: FactState }) {
  const style = STATE_STYLES[state];
  if (!style.label) return null;
  return (
    <span
      data-state={state}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-medium ${style.chip}`}
    >
      <span aria-hidden="true">{style.glyph}</span>
      {style.label}
    </span>
  );
}
