/// The shapes the backend actually returns.
///
/// Deliberately separate from `src/types.ts`, which describes what the *screens*
/// want. The two are not the same thing and should not be made the same thing:
/// the API speaks in decided clinical facts, the screens speak in cards and
/// sections, and `adapt.ts` is the one place that translates. Collapsing them
/// would mean every component learning the wire format, and a wire change
/// touching every component.

export interface ApiWorklistEntry {
  intake_id: string;
  department_code: string | null;
  state: 'red_flag_pending' | 'ready' | 'needs_review' | 'partial' | 'seen';
  intake_status: string;
  arrived_at: string;
  language: string;
  unacknowledged_alerts: number;
  unresolved_count: number;
  contradiction_count: number;
  needs_verification: boolean;
  repaired: boolean;
  needs_manual_review: boolean;
  patient_ref_type: 'guest' | 'phone' | 'hospital_id' | 'abha_address';
  seen_at: string | null;
}

export interface ApiWorklist {
  department_code: string | null;
  entries: ApiWorklistEntry[];
  pending_alerts: unknown[];
  total: number;
  generated_at: string;
  demo: boolean;
}

/** A fact's value. `kind` decides which of the other keys is meaningful. */
export interface ApiFactValue {
  kind: 'text' | 'boolean' | 'duration' | 'scale' | 'coded' | 'quantity';
  text?: string;
  value?: boolean | number;
  magnitude?: number;
  unit?: string;
  code?: string;
  system?: string | null;
  display?: string | null;
  minimum?: number;
  maximum?: number;
}

/**
 * One decided clinical fact.
 *
 * `status` carries the five-status vocabulary and must never be collapsed to a
 * boolean here: `unresolved` (asked, no answer), `not_asked`, `not_applicable`
 * and `refused` mean four different things to a physician, and a screen that
 * renders them all as "—" has told them the same thing four times.
 */
export interface ApiFact {
  fact_id: string;
  field_id: string;
  label: string;
  status: 'answered' | 'unresolved' | 'not_asked' | 'not_applicable' | 'refused';
  value: ApiFactValue | null;
  rendered: string | null;
  original_text: string | null;
  language: string | null;
  certainty: string | null;
  channel: string | null;
  section: string | null;
  confidence: number | null;
  physician_verified: boolean;
  physician_action: string | null;
  repaired: boolean;
  needs_verification: boolean;
  carried_forward: unknown;
  source: {
    kind: string;
    turn_id: number | null;
    question_id: string | null;
    transcript_excerpt: string | null;
  } | null;
  recorded_at: string;
}

export interface ApiRedFlag {
  rule_id: string;
  label?: string | null;
  severity?: string;
  acknowledged?: boolean;
  fired_at_turn?: number | null;
}

export interface ApiDocument {
  document_id: string;
  kind: string;
  status?: string;
  captured_at?: string | null;
  items?: Array<{ label?: string; value?: string; text?: string }>;
}

export interface ApiIntake {
  intake_id: string;
  hospital_id: string;
  status: string;
  language: string;
  department_code: string | null;
  patient_ref: { type: string; value: string | null };
  facts: ApiFact[];
  red_flags: ApiRedFlag[];
  documents: ApiDocument[];
  contradictions: unknown[];
  unresolved_fields: string[];
  needs_review: boolean;
  provenance: {
    schema_version: string;
    engine_version: string | null;
    content_version: string | null;
    kiosk_id: string | null;
    repaired: boolean;
    needs_manual_review: boolean;
  };
  received_at: string;
  seen_at: string | null;
  demo: boolean;
}

export interface ApiHospital {
  hospital_id: string;
  display_name: string;
  location?: string;
  timezone?: string;
  default_language?: string;
  departments?: Array<{ code: string; display_name?: string }>;
}
