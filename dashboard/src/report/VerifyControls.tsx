/**
 * Accept, amend or reject — 3/3 §6.
 *
 * **Amending opens an inline editor, not a modal.** The consultation is two
 * minutes; a dialog that steals focus, has to be dismissed, and loses the
 * physician's place in the report costs more of those two minutes than the
 * correction is worth.
 *
 * Rejecting asks for confirmation and says what it means, because "reject" is
 * ambiguous in a way that matters clinically: it records that the field was
 * **never established**, not that the answer is no. The backend enforces that
 * (`Fact.rejected_by_physician`); this wording is so a physician is not
 * surprised by it.
 */
import { useState } from 'react';

import type { Fact, FactValue } from '../api/types';
import type { FactAction } from '../api/queries';

export function VerifyControls({
  fact,
  onAct,
  pending,
}: {
  fact: Fact;
  onAct: (action: FactAction) => void;
  pending: boolean;
}) {
  const [mode, setMode] = useState<'idle' | 'amending' | 'rejecting'>('idle');

  if (fact.physician_action === 'verified' || fact.physician_action === 'amended') {
    return (
      <span className="shrink-0 self-center text-xs text-verified">
        {fact.physician_action === 'amended' ? 'corrected' : 'verified'}
      </span>
    );
  }

  if (mode === 'amending') {
    return (
      <AmendEditor
        fact={fact}
        pending={pending}
        onCancel={() => setMode('idle')}
        onSubmit={(value, reason) => {
          onAct({ factId: fact.fact_id, action: 'amended', value, reason });
          setMode('idle');
        }}
      />
    );
  }

  if (mode === 'rejecting') {
    return (
      <div className="shrink-0 self-center rounded border border-conflict/40 bg-conflict-soft p-2 text-xs">
        <p className="max-w-xs text-conflict">
          This records that the field was <strong>never established</strong> —
          not that the answer is no.
        </p>
        <div className="mt-1 flex gap-1">
          <button
            type="button"
            data-testid="reject-confirm"
            disabled={pending}
            onClick={() => {
              onAct({ factId: fact.fact_id, action: 'rejected' });
              setMode('idle');
            }}
            className="rounded bg-conflict px-2 py-1 font-medium text-white"
          >
            Confirm
          </button>
          <button
            type="button"
            onClick={() => setMode('idle')}
            className="rounded border border-line px-2 py-1 text-ink"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <span className="flex shrink-0 gap-1 self-center opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100">
      <Action
        label="Accept"
        testId="accept"
        disabled={pending || fact.status !== 'answered'}
        title={
          fact.status === 'answered'
            ? 'Confirm this as recorded'
            : 'Nothing to confirm — this field was never answered'
        }
        onClick={() => onAct({ factId: fact.fact_id, action: 'verified' })}
      />
      <Action
        label="Amend"
        testId="amend"
        disabled={pending}
        onClick={() => setMode('amending')}
      />
      <Action
        label="Reject"
        testId="reject"
        disabled={pending || fact.status !== 'answered'}
        onClick={() => setMode('rejecting')}
      />
    </span>
  );
}

function Action({
  label,
  testId,
  onClick,
  disabled,
  title,
}: {
  label: string;
  testId: string;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="rounded border border-line px-1.5 py-0.5 text-xs text-ink hover:bg-surface-sunken disabled:opacity-40"
    >
      {label}
    </button>
  );
}

/**
 * The inline editor.
 *
 * It edits the value **in the shape the record holds**, not as free text. A
 * duration is a magnitude and a unit; typing "about five days" into a text box
 * would either be rejected by the backend or stored as a `Text` value where a
 * `Duration` belongs, and the report would stop being comparable with itself.
 */
function AmendEditor({
  fact,
  onSubmit,
  onCancel,
  pending,
}: {
  fact: Fact;
  onSubmit: (value: FactValue, reason?: string) => void;
  onCancel: () => void;
  pending: boolean;
}) {
  const existing = (fact.value ?? {}) as Record<string, unknown>;
  const kind = (existing.kind as string | undefined) ?? 'text';
  const [draft, setDraft] = useState(() => initialDraft(kind, existing));
  const [unit, setUnit] = useState(String(existing.unit ?? 'day'));
  const [reason, setReason] = useState('');

  return (
    <form
      data-testid="amend-editor"
      className="shrink-0 self-center rounded border border-accent/40 bg-accent-soft p-2 text-xs"
      onSubmit={(event) => {
        event.preventDefault();
        const value = buildValue(kind, draft, unit, existing);
        if (value === null) return;
        onSubmit(value, reason || undefined);
      }}
    >
      <div className="flex items-center gap-1">
        {kind === 'boolean' ? (
          <select
            aria-label="Corrected value"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="rounded border border-line bg-surface px-1.5 py-1 text-ink"
          >
            <option value="true">yes</option>
            <option value="false">no</option>
          </select>
        ) : (
          <input
            aria-label="Corrected value"
            value={draft}
            autoFocus
            onChange={(event) => setDraft(event.target.value)}
            className="w-32 rounded border border-line bg-surface px-1.5 py-1 text-ink"
          />
        )}
        {(kind === 'duration' || kind === 'quantity') && (
          <input
            aria-label="Unit"
            value={unit}
            onChange={(event) => setUnit(event.target.value)}
            className="w-20 rounded border border-line bg-surface px-1.5 py-1 text-ink"
          />
        )}
        <button
          type="submit"
          data-testid="amend-save"
          disabled={pending}
          className="rounded bg-accent px-2 py-1 font-medium text-white"
        >
          Save
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-line px-2 py-1 text-ink"
        >
          Cancel
        </button>
      </div>
      <input
        aria-label="Reason"
        placeholder="Reason (optional)"
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        className="mt-1 w-full rounded border border-line bg-surface px-1.5 py-1 text-ink"
      />
      {/* The patient's words stay put. An amendment corrects the normalised
          value; it does not revise what the patient said. */}
      {fact.original_text && (
        <p className="mt-1 max-w-xs text-ink-muted">
          Heard: <span lang={fact.language ?? undefined}>{fact.original_text}</span>
        </p>
      )}
    </form>
  );
}

function initialDraft(kind: string, existing: Record<string, unknown>): string {
  switch (kind) {
    case 'boolean':
      return existing.value ? 'true' : 'false';
    case 'quantity':
    case 'duration':
    case 'scale':
      return String(existing.magnitude ?? existing.value ?? '');
    case 'coded':
      return String(existing.display ?? existing.code ?? '');
    case 'date':
      return String(existing.value ?? '');
    default:
      return String(existing.text ?? '');
  }
}

/** The draft as a `FactValue`, or `null` when it is not one yet. */
function buildValue(
  kind: string,
  draft: string,
  unit: string,
  existing: Record<string, unknown>,
): FactValue | null {
  const trimmed = draft.trim();
  if (!trimmed) return null;
  switch (kind) {
    case 'boolean':
      return { kind: 'boolean', value: trimmed === 'true' };
    case 'quantity': {
      const magnitude = Number(trimmed);
      if (Number.isNaN(magnitude) || !unit.trim()) return null;
      return { kind: 'quantity', magnitude, unit: unit.trim() };
    }
    case 'duration': {
      const magnitude = Number(trimmed);
      const allowed = ['hour', 'day', 'week', 'month', 'year'] as const;
      const chosen = allowed.find((candidate) => candidate === unit.trim());
      if (Number.isNaN(magnitude) || !chosen) return null;
      return { kind: 'duration', magnitude, unit: chosen };
    }
    case 'scale': {
      const value = Number(trimmed);
      if (Number.isNaN(value)) return null;
      return {
        kind: 'scale',
        value,
        minimum: Number(existing.minimum ?? 0),
        maximum: Number(existing.maximum ?? 10),
      };
    }
    case 'coded':
      // The code stays; only the display changes. A physician correcting the
      // wording of a coded term has not chosen a different term, and silently
      // reassigning the code would change what the record means.
      return {
        kind: 'coded',
        code: String(existing.code ?? trimmed),
        system: (existing.system as string | undefined) ?? null,
        display: trimmed,
      };
    case 'date':
      return { kind: 'date', value: trimmed, precision: 'day' };
    default:
      return { kind: 'text', text: trimmed };
  }
}
