/**
 * The backend's own types, named — 3/3 §3.
 *
 * Every name here is an alias into `schema.d.ts`, which is generated from the
 * backend's OpenAPI document by `npm run api:types`. **Nothing in this file is
 * hand-written structure.** A hand-written `FactOut` drifts from the backend
 * the first time a field is added, and the way you find out is a physician
 * looking at a report with a line missing.
 *
 * The two exceptions are at the bottom, and both are honest about what they
 * are: `PhysicianReport` shapes a field the backend types as an open object,
 * and `Evidence` shapes an endpoint that returns a raw dict. Both are marked.
 */
import type { components } from './schema';

type S = components['schemas'];

export type Fact = S['FactOut'];
export type Intake = S['IntakeOut'];
export type Report = S['ReportOut'];
export type Worklist = S['WorklistOut'];
export type WorklistEntry = S['WorklistEntryOut'];
export type Alert = S['AlertOut'];
export type AlertList = S['AlertListOut'];
export type CorrectionRate = S['CorrectionRateOut'];
export type PhysicianAction = S['PhysicianAction'];
export type FactValue = NonNullable<S['FactVerifyRequest']['value']>;
export type FactVerifyRequest = S['FactVerifyRequest'];
export type DocumentRef = S['DocumentOut'];
/**
 * `Fact.carried_forward`, which OpenAPI types as an open object. Shaped here to
 * match `app/domain/record.py::CarriedForward`.
 *
 * `confirmed_today` is three-valued and stays that way: `null` means the
 * question was not put today, which is not the patient declining to confirm.
 */
export interface CarriedForward {
  from_intake_id: string;
  /** ISO date, `YYYY-MM-DD`. */
  originally_recorded: string;
  confirmed_today?: boolean | null;
}

/** The vocabulary a worklist row can show. From `app/domain/worklist.py`. */
export const WORKLIST_STATES = [
  'ready',
  'partial',
  'red_flag_pending',
  'needs_review',
  'seen',
] as const;
export type WorklistState = (typeof WORKLIST_STATES)[number];

/** How the intake ended on the device. From `app/domain/record.py`. */
export type IntakeStatus =
  | 'complete'
  | 'partial'
  | 'aborted_red_flag'
  | 'abandoned';

/**
 * `ReportOut.report`, which OpenAPI types as an open object because the
 * builder's model is not part of the request/response schema. Shaped here to
 * match `app/domain/report/model.py::PhysicianReport` exactly.
 *
 * Every field is optional on read. The dashboard renders what arrived; a
 * missing section is an empty section, never a crash on a clinical screen.
 */
export interface LineMarker {
  code: string;
  text: string;
}

export interface ReportLine {
  text: string;
  /**
   * The two halves of `text`, when it has two — the builder states them so this
   * screen does not have to split on `": "`, which would be the dashboard
   * deriving structure (§12). Both null on a line that is a sentence rather
   * than a pair, and then `text` is what to render.
   */
  label?: string | null;
  value?: string | null;
  field_ids?: readonly string[];
  fact_ids?: readonly string[];
  sources?: readonly Record<string, unknown>[];
  markers?: readonly LineMarker[];
  original_text?: string | null;
  original_language?: string | null;
}

export interface ReportSection {
  section: string;
  title: string;
  lines: readonly ReportLine[];
}

/** One half of a conflict. `app/domain/record.py::ConflictSide`. */
export interface ConflictSide {
  fact_id: string;
  statement: string;
  channel: string;
  source_label: string;
  confidence?: number | null;
  original_text?: string | null;
}

/**
 * A disagreement between two facts about the same field.
 *
 * `resolution` is always "Physician verification required" — the backend never
 * picks a winner and neither does this screen.
 */
export interface Contradiction {
  field_id: string;
  kind: 'status' | 'value' | 'presence_only_in_record' | string;
  reported_today?: ConflictSide | null;
  from_record: ConflictSide;
  resolution: string;
}

export interface RedFlagLine {
  rule_id: string;
  severity: string;
  label?: string | null;
  criteria_met?: readonly string[];
  acknowledged_by?: string | null;
  acknowledged_at?: string | null;
}

export interface InteractionLine {
  text: string;
  severity: string;
  source: string;
}

/**
 * Where one uploaded document sits in time relative to this intake.
 * `app/domain/report/model.py::TimelineEntry`.
 *
 * `dated: false` is the line's whole point: a document with no legible date
 * cannot be placed at all, and that is a problem to state rather than hide.
 */
export interface TimelineEntry {
  document_id: string;
  document_date?: string | null;
  days_before_intake?: number | null;
  dated: boolean;
  text: string;
  fact_ids?: readonly string[];
}

/**
 * The medical history timeline — `app/domain/timeline/model.py`.
 *
 * `status` is not decoration. A reader cannot tell "not built yet" from
 * "nothing on record" from "a selection" by looking at the list, and the three
 * mean very different things.
 */
export type TimelineStatus = 'unfiltered' | 'filtered' | 'pending';

export interface ClinicalEvent {
  event_date: string;
  kind: 'visit' | 'document' | 'medication' | 'investigation' | string;
  label: string;
  source?: 'deterministic' | 'model_selected' | string;
  intake_id?: string | null;
  document_id?: string | null;
  candidate_id?: string | null;
  relevance?: number;
  relevance_reason?: string | null;
}

export interface TimelineSnapshot {
  status: TimelineStatus;
  events?: readonly ClinicalEvent[];
  /** How many earlier events were judged unrelated and left out. */
  omitted_count?: number;
  provider?: string | null;
  model_id?: string | null;
  generated_at?: string | null;
}

export interface PhysicianReport {
  intake_id: string;
  hospital_id: string;
  language: string;
  template_version?: string;
  sections?: readonly ReportSection[];
  unresolved?: readonly ReportLine[];
  conflicts?: readonly Contradiction[];
  alerts?: readonly RedFlagLine[];
  interactions?: readonly InteractionLine[];
  document_timeline?: readonly TimelineEntry[];
  /** `null` means not built yet — which the screen says, rather than showing
   *  an empty section. */
  history?: TimelineSnapshot | null;
  document_notes?: readonly ReportLine[];
  /** Display label for every field id the report mentions. */
  field_labels?: Readonly<Record<string, string>>;
  contains_repaired?: boolean;
  needs_verification?: boolean;
  demo?: boolean;
  generated_at?: string | null;
  physician_verified_by?: string | null;
}

/**
 * `GET /intakes/{id}/facts/{fact_id}/evidence`, which the backend types as a
 * raw dict. `src/evidence/fromApi.ts` narrows this into what the panel renders.
 */
export interface EvidencePayload {
  fact_id: string;
  field_id: string;
  status: string;
  value?: Record<string, unknown> | null;
  original_text?: string | null;
  language?: string | null;
  certainty: string;
  channel: string;
  confidence?: number | null;
  repaired?: boolean;
  needs_verification?: boolean;
  physician_verified?: boolean;
  physician_action?: string | null;
  carried_forward?: CarriedForward | null;
  source: Record<string, unknown>;
  recorded_at: string;
  supersedes?: string | null;
}
