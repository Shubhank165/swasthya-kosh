/**
 * The backend's evidence payload, as the panel renders it — 3/3 §5.
 *
 * Pure, and separate from the component, because this is where the two
 * vocabularies meet and that is worth testing on its own. The backend speaks
 * `FactChannel` — `voice`, `touch`, `document`, `prior_record`, `staff` — and
 * the panel speaks in terms of what a physician is about to look at: a
 * transcript turn, a boxed region of a scan, a tapped option, a previous visit.
 *
 * `touch` maps to `app` and that is not cosmetic. A tap has no ASR confidence
 * and no spoken original, and rendering it through the voice branch would show
 * an empty confidence and an empty quotation — an answer looking less
 * evidenced than it is.
 *
 * Nothing here interprets. It moves fields.
 */
import type { EvidencePayload } from '../api/types';
import type { Evidence } from './EvidencePanel';

interface TurnSource {
  kind: 'turn';
  turn_id: number;
  question_id?: string | null;
  transcript_excerpt?: string | null;
}

interface DocumentSourceRef {
  kind: 'document';
  document_id: string;
  page: number;
  bbox?: { x: number; y: number; width: number; height: number } | null;
}

interface EntrySourceRef {
  kind: 'entry';
  entered_by: string;
  prior_intake_id?: string | null;
}

type AnySource = TurnSource | DocumentSourceRef | EntrySourceRef;

/** What the panel needs that the fact itself cannot supply. */
export interface EvidenceContext {
  /** The question the device asked, by `question_id`, when the bundle is loaded. */
  questionText?: (questionId: string) => string | undefined;
  /** Signed URL for a document page, by `document_id`. */
  documentUrl?: (documentId: string) => string | undefined;
}

export function evidenceFromApi(
  payload: EvidencePayload,
  context: EvidenceContext = {},
): Evidence {
  const source = payload.source as unknown as AnySource;

  // Carry-forward first, whatever the channel says. A fact brought over from
  // June is best explained by the visit it came from, and its source is an
  // `entry` that would otherwise fall through to the default branch.
  if (payload.carried_forward) {
    return {
      channel: 'carried_forward',
      from_intake_id: payload.carried_forward.from_intake_id,
      originally_recorded: payload.carried_forward.originally_recorded,
      confirmed_today: payload.carried_forward.confirmed_today ?? null,
      transcript: payload.original_text ?? null,
      language: payload.language ?? null,
    };
  }

  if (source?.kind === 'document') {
    return {
      channel: 'document',
      image_url: context.documentUrl?.(source.document_id) ?? null,
      page: source.page,
      bounding_box: source.bbox ?? null,
      // The extracted value and the raw text, always both. A value the
      // physician cannot compare with what is on the paper is an assertion.
      extracted_value: renderValue(payload.value),
      raw_text: payload.original_text ?? null,
      ocr_confidence: payload.confidence ?? null,
    };
  }

  if (payload.channel === 'touch') {
    return {
      channel: 'app',
      question: questionFor(source, context),
      chosen_option: renderValue(payload.value) ?? payload.original_text ?? null,
      language: payload.language ?? null,
    };
  }

  if (payload.channel === 'voice' && source?.kind === 'turn') {
    return {
      channel: 'voice',
      question: questionFor(source, context),
      // The patient's own words. Never translated in place (§9); the panel
      // puts a translation beneath when one exists, and there is none here
      // because the backend does not translate either.
      transcript: source.transcript_excerpt ?? payload.original_text ?? null,
      language: payload.language ?? null,
      asr_confidence: payload.confidence ?? null,
    };
  }

  // Staff entry, or a source shape this build does not know. Rendered as a
  // plain entry rather than dropped: a fact whose evidence panel is blank looks
  // like a bug, and a fact whose evidence is "a person typed this" is a fact
  // with real, if thin, provenance.
  return {
    channel: 'entry',
    question: null,
    transcript: payload.original_text ?? renderValue(payload.value),
    language: payload.language ?? null,
    entered_by: source?.kind === 'entry' ? source.entered_by : null,
  };
}

function questionFor(
  source: AnySource | undefined,
  context: EvidenceContext,
): string | null {
  if (source?.kind !== 'turn' || !source.question_id) return null;
  return context.questionText?.(source.question_id) ?? null;
}

/**
 * A `FactValue` as text.
 *
 * Mirrors `render()` in `app/domain/record.py`, and that duplication is a
 * deliberate, bounded one: the evidence endpoint returns the raw value rather
 * than the rendering, and the alternative — showing `{"kind":"duration",...}`
 * to a physician — is worse than seven lines of switch.
 */
export function renderValue(value: Record<string, unknown> | null | undefined): string | null {
  if (!value) return null;
  switch (value.kind) {
    case 'quantity':
      return `${trim(value.magnitude)} ${String(value.unit)}`;
    case 'duration': {
      const magnitude = trim(value.magnitude);
      return `${magnitude} ${String(value.unit)}${magnitude === '1' ? '' : 's'}`;
    }
    case 'coded':
      return (
        (value.display as string | null) ??
        String(value.code ?? '').replace(/_/g, ' ')
      );
    case 'text':
      return String(value.text ?? '');
    case 'boolean':
      return value.value ? 'yes' : 'no';
    case 'date':
      return String(value.value ?? '');
    case 'scale':
      return `${trim(value.value)}/${trim(value.maximum)}`;
    default:
      return null;
  }
}

function trim(raw: unknown): string {
  const numeric = Number(raw);
  return Number.isInteger(numeric) ? String(numeric) : String(numeric);
}
