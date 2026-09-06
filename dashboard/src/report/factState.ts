/**
 * How much to trust one line — 3/3 §1 rule 3, §4.2.
 *
 * **The dashboard never computes clinical content** (§1 rule 1). Nothing here
 * decides whether a fact is true, complete or concerning; it reads what the
 * backend already concluded and decides how it should *look*. The distinction
 * matters: the moment this file starts inferring "low confidence means probably
 * wrong", the dashboard has an opinion, and §12 forbids it having one.
 *
 * Every state carries a **label and a shape**, not only a colour. Some
 * reviewers are colour-blind and all of them will be looking at a projector —
 * and more to the point, a doctor reading this at speed should be able to tell
 * a reconstructed line from a verified one in peripheral vision.
 */

/** The backend's marker codes, from `app/domain/report/model.py`. */
export type MarkerCode = 'uncertain' | 'repaired' | 'verify' | 'approximate' | 'attendant';

export type FactState =
  | 'confirmed'
  | 'verified'
  | 'unresolved'
  | 'not_asked'
  | 'not_applicable'
  | 'repaired'
  | 'low_confidence'
  | 'approximate'
  | 'second_hand'
  | 'carried_forward'
  | 'conflicting';

export interface StateStyle {
  /** Shown to the physician. Never a diagnosis, never a likelihood. */
  label: string;
  /** A glyph, so the state survives greyscale and peripheral vision. */
  glyph: string;
  /** Tailwind classes for the chip. */
  chip: string;
  /** Whether the patient's own words must be shown beside the line. */
  showsOriginal: boolean;
}

/**
 * The one place a state becomes a look.
 *
 * `not_asked` and `unresolved` are deliberately different entries with
 * different wording. They are different medico-legal positions — nobody asked,
 * versus the patient could not say — and §4.2 requires that a reader can tell
 * them apart without knowing the vocabulary.
 */
export const STATE_STYLES: Record<FactState, StateStyle> = {
  confirmed: {
    label: '',
    glyph: '',
    chip: '',
    showsOriginal: false,
  },
  verified: {
    label: 'verified by physician',
    glyph: '✓',
    chip: 'bg-verified-soft text-verified border-verified/30',
    showsOriginal: false,
  },
  unresolved: {
    // "Not established", never "no" and never blank — §1 rule 3.
    label: 'not established',
    glyph: '◌',
    chip: 'bg-uncertain-soft text-uncertain border-uncertain/30',
    showsOriginal: false,
  },
  not_asked: {
    label: 'not asked',
    glyph: '—',
    chip: 'bg-surface-sunken text-ink-muted border-line',
    showsOriginal: false,
  },
  not_applicable: {
    label: 'not applicable',
    glyph: '⊘',
    chip: 'bg-surface-sunken text-ink-muted border-line',
    showsOriginal: false,
  },
  repaired: {
    label: 'reconstructed from unclear input',
    glyph: '⟳',
    chip: 'bg-repaired-soft text-repaired border-repaired/30',
    // The original is the whole point: a reconstruction the physician cannot
    // check against what was actually said is an assertion.
    showsOriginal: true,
  },
  low_confidence: {
    label: 'low-confidence reading',
    glyph: '?',
    chip: 'bg-uncertain-soft text-uncertain border-uncertain/30',
    showsOriginal: true,
  },
  approximate: {
    label: 'approximate',
    glyph: '≈',
    chip: 'bg-uncertain-soft text-uncertain border-uncertain/30',
    showsOriginal: false,
  },
  second_hand: {
    label: 'reported by an attendant',
    glyph: '⇉',
    chip: 'bg-surface-sunken text-ink-muted border-line',
    showsOriginal: false,
  },
  carried_forward: {
    label: 'from a previous visit',
    glyph: '↩',
    chip: 'bg-accent-soft text-accent border-accent/30',
    showsOriginal: false,
  },
  conflicting: {
    label: 'conflicting accounts',
    glyph: '⚠',
    chip: 'bg-conflict-soft text-conflict border-conflict/30',
    showsOriginal: true,
  },
};

/** Marker code to state, for the codes that map one-to-one. */
const MARKER_STATES: Partial<Record<MarkerCode, FactState>> = {
  repaired: 'repaired',
  verify: 'low_confidence',
  uncertain: 'low_confidence',
  approximate: 'approximate',
  attendant: 'second_hand',
};

export interface LineLike {
  markers?: readonly { code: string; text: string }[];
}

export interface FactLike {
  status?: string;
  physician_verified?: boolean;
  repaired?: boolean;
  needs_verification?: boolean;
  confidence?: number | null;
  carried_forward?: unknown;
}

/**
 * Every state that applies to one line, most-qualifying first.
 *
 * A list rather than a single value, because a line can be several things at
 * once — a repaired, low-confidence, attendant-reported answer is all three,
 * and collapsing that to the "worst" one hides two of them. §1 rule 3:
 * uncertainty is displayed, never smoothed.
 */
export function statesFor(line: LineLike, fact?: FactLike): FactState[] {
  const states = new Set<FactState>();

  if (fact?.physician_verified) states.add('verified');

  switch (fact?.status) {
    case 'unresolved':
      states.add('unresolved');
      break;
    case 'not_asked':
      states.add('not_asked');
      break;
    case 'not_applicable':
      states.add('not_applicable');
      break;
    case 'refused':
      // The patient declined. Not "no", and not an absence.
      states.add('unresolved');
      break;
    default:
      break;
  }

  if (fact?.repaired) states.add('repaired');
  if (fact?.needs_verification) states.add('low_confidence');
  if (fact?.carried_forward) states.add('carried_forward');

  for (const marker of line.markers ?? []) {
    const mapped = MARKER_STATES[marker.code as MarkerCode];
    if (mapped) states.add(mapped);
  }

  // `confirmed` is the absence of every qualifier, not a state the backend
  // sends. Returning it explicitly keeps the caller from having to special-case
  // an empty list.
  if (states.size === 0) states.add('confirmed');
  return [...states];
}
