/// Backend facts -> what the screens render.
///
/// **The two-vocabularies problem this file exists to solve.**
///
/// The same clinical idea reaches the dashboard under two different field ids
/// depending on which device took the intake. The Jetson kiosk runs its own
/// question bank and emits bare names — `chief_complaint`, `severity`, `age`.
/// The phone app walks the compiled question bundle and emits namespaced ones —
/// `routing.chief_complaint`, `general.severity`, `general.age`. Neither is
/// wrong; they are two devices with two content sets, and the backend files
/// both faithfully rather than flattening them at the door.
///
/// A component that reads `fields['chief_complaint']` therefore renders a
/// kiosk intake and shows nothing at all for an app one. So the map this file
/// builds is keyed by the field's own id **and** by every alias for it, and a
/// screen may ask under either spelling. Aliasing is one-way into a lookup
/// table — it never rewrites the fact, and `field_id` on the fact stays exactly
/// what the device sent, because that is what a physician's audit trail points
/// at.
///
/// Nothing here decides anything clinical. Statuses are carried through
/// untouched, `rendered` is the backend's own text, and a value this file does
/// not understand is passed along rather than guessed at.

import type {
  FieldItem,
  FieldValue,
  IntakeData,
  PatientQueueItem,
  Turn,
} from '../types';
import type { ApiFact, ApiIntake, ApiWorklistEntry } from './types';

/**
 * Canonical id -> every spelling that means it.
 *
 * Only pairs that are genuinely the same question belong here. `screen_fever`
 * and `fever.measured` are *not* the same claim — one is a yes/no screening
 * question, the other is whether a temperature was actually taken — and
 * merging them would put a finding on a physician's sheet that no question
 * established. They are deliberately absent.
 */
const ALIASES: Record<string, string[]> = {
  chief_complaint: ['routing.chief_complaint'],
  duration: ['general.duration'],
  severity: ['general.severity', 'pain.severity'],
  onset: ['general.onset', 'pain.onset'],
  age: ['general.age', 'history.age', 'registration.age'],
  sex: ['general.sex'],
  reporter: ['general.reporter', 'reporter_role'],
  previous_episodes: ['general.previous_episodes'],
  relieving_factors: ['general.relieving', 'pain.relieving_factors'],
  aggravating_triggers: ['general.aggravating', 'pain.aggravating_factors'],
  progression: ['general.progression', 'pain.progression'],
  pattern: ['general.pattern', 'pain.pattern'],
  current_medications: ['general.medications'],
  allergy: ['general.allergies'],
  heart_rate_bpm: ['vitals.heart_rate'],
};

/** Every alias, both directions, flattened once at module load. */
const EQUIVALENTS: Record<string, string[]> = (() => {
  const out: Record<string, string[]> = {};
  const add = (from: string, to: string) => {
    (out[from] ??= []).push(to);
  };
  for (const [canonical, spellings] of Object.entries(ALIASES)) {
    for (const spelling of spellings) {
      add(spelling, canonical);
      add(canonical, spelling);
      for (const sibling of spellings) if (sibling !== spelling) add(spelling, sibling);
    }
  }
  return out;
})();

function toFieldValue(fact: ApiFact): FieldValue | undefined {
  if (fact.value === null) return undefined;
  // Structurally the same object; typed separately so a wire change surfaces
  // here rather than inside a card.
  return fact.value as FieldValue;
}

function toFieldItem(fact: ApiFact): FieldItem {
  const item: FieldItem = {
    // `not_asked` and `refused` have no home in the screens' narrower union.
    // They are carried as `unresolved`, which is the honest reading of both for
    // a renderer: the question produced no answer. The untouched status stays
    // reachable on the fact itself for anything that needs the distinction.
    status:
      fact.status === 'answered' || fact.status === 'not_applicable'
        ? fact.status
        : 'unresolved',
  };
  const value = toFieldValue(fact);
  if (value !== undefined && fact.status === 'answered') item.value = value;
  if (fact.original_text) item.original_text = fact.original_text;
  if (fact.language) item.language = fact.language;
  if (fact.source?.turn_id) item.source_turn = fact.source.turn_id;
  if (fact.confidence !== null) item.confidence = fact.confidence;
  return item;
}

/**
 * Turns, rebuilt from the facts that name them.
 *
 * The detail endpoint does not serve the turn list — a turn is only reachable
 * through the fact it bound — so this recovers what it can and no more. A fact
 * with no `source.turn_id` contributes no turn rather than an invented one.
 */
function rebuildTurns(facts: ApiFact[]): Turn[] {
  const byTurn = new Map<number, Turn>();
  for (const fact of facts) {
    const turnId = fact.source?.turn_id;
    if (!turnId || byTurn.has(turnId)) continue;
    byTurn.set(turnId, {
      turn_id: turnId,
      question_id: fact.source?.question_id ?? fact.field_id,
      transcript: fact.source?.transcript_excerpt ?? null,
      bound_field: fact.field_id,
      resolved: fact.status === 'answered',
      asr_confidence: fact.confidence,
    });
  }
  return [...byTurn.values()].sort((a, b) => a.turn_id - b.turn_id);
}

/** Camera vitals, only when the kiosk sent a reading it would vouch for. */
function cameraVitals(fields: Record<string, FieldItem>): IntakeData['cameraVitals'] {
  const heartRate = fields['heart_rate_bpm'];
  if (!heartRate || heartRate.status !== 'answered') return undefined;
  const bpm =
    heartRate.value?.magnitude ??
    (typeof heartRate.value?.value === 'number' ? heartRate.value.value : undefined);
  if (bpm === undefined) return undefined;
  return {
    heartRateBpm: Math.round(bpm),
    // The kiosk sends a heart rate and nothing else. Reporting a respiratory
    // rate it never measured would be inventing a vital sign, so this is 0 and
    // the card is expected to omit what it has no number for.
    respiratoryRateBpm: 0,
    confidence: heartRate.confidence ?? 0,
    sensorType: 'rPPG (camera estimate)',
    extractionDurationSec: 0,
    timestamp: new Date().toISOString(),
    qualityIndex: (heartRate.confidence ?? 0) >= 0.8 ? 'Good' : 'Fair',
  };
}

/** One intake, in the shape the screens read. */
export function toIntakeData(intake: ApiIntake): IntakeData {
  const fields: Record<string, FieldItem> = {};
  for (const fact of intake.facts) {
    const item = toFieldItem(fact);
    fields[fact.field_id] = item;
    // Aliases fill gaps; they never overwrite a field the device actually sent.
    for (const alias of EQUIVALENTS[fact.field_id] ?? []) {
      if (!(alias in fields)) fields[alias] = item;
    }
  }

  return {
    schema_version: intake.provenance.schema_version,
    intake_id: intake.intake_id,
    kiosk_id: intake.provenance.kiosk_id,
    hospital_id: intake.hospital_id,
    status: intake.status,
    language: intake.language,
    reporter: fields['reporter']?.value?.text ?? 'self',
    department_code: intake.department_code,
    patient_ref: {
      type: (intake.patient_ref.type as IntakeData['patient_ref']['type']) ?? 'guest',
      value: intake.patient_ref.value,
    },
    engine_version: intake.provenance.engine_version,
    content_version: intake.provenance.content_version ?? '',
    // The kiosk stamps itself; the app does not. That absence is the only
    // reliable way to tell the two apart, and it is what the device chose to
    // say about itself rather than a guess made here.
    source: intake.provenance.kiosk_id ? 'kiosk' : 'app',
    turns: rebuildTurns(intake.facts),
    fields,
    red_flags: intake.red_flags.map((flag) => flag.label || flag.rule_id),
    cameraVitals: cameraVitals(fields),
  };
}

function firstText(fields: Record<string, FieldItem>, ids: string[]): string | undefined {
  for (const id of ids) {
    const item = fields[id];
    if (item?.status !== 'answered') continue;
    const value = item.value;
    const text = value?.text ?? value?.display ?? value?.code ?? item.original_text;
    if (text) return String(text);
  }
  return undefined;
}

function firstNumber(fields: Record<string, FieldItem>, ids: string[]): number | undefined {
  for (const id of ids) {
    const item = fields[id];
    if (item?.status !== 'answered') continue;
    const value = item.value;
    const n = value?.magnitude ?? (typeof value?.value === 'number' ? value.value : undefined);
    if (typeof n === 'number') return n;
  }
  return undefined;
}

/**
 * A queue row.
 *
 * The queue endpoint carries no name, no token and no vitals — a patient may be
 * a guest, and the record is keyed by a peppered phone digest rather than
 * anything printable. So the row shows what the record actually knows: the
 * reference type, the arrival position, and whatever the interview established.
 * Inventing a plausible name here would put a person on a physician's screen
 * who does not exist.
 */
export function toQueueItem(
  entry: ApiWorklistEntry,
  intake: ApiIntake,
  position: number,
): PatientQueueItem {
  const data = toIntakeData(intake);
  const fields = data.fields;
  const complaint = firstText(fields, ['chief_complaint', 'routing.chief_complaint']);

  return {
    id: entry.intake_id,
    tokenNumber: `OPD-${String(101 + position)}`,
    name: `Patient #${entry.intake_id.slice(0, 8)}`,
    age: Math.round(firstNumber(fields, ['age']) ?? 0),
    gender: firstText(fields, ['sex']) ?? 'Not recorded',
    source: data.source ?? 'app',
    kioskId: data.kiosk_id ?? undefined,
    abhaNumber: entry.patient_ref_type === 'abha_address' ? (intake.patient_ref.value ?? '') : '',
    abhaVerified: entry.patient_ref_type === 'abha_address',
    chiefComplaint: complaint ?? 'Not recorded',
    severity: Math.round(firstNumber(fields, ['severity']) ?? 0),
    vitalsSummary: {
      hr: data.cameraVitals?.heartRateBpm ?? 0,
      rr: data.cameraVitals?.respiratoryRateBpm ?? 0,
      spo2: data.cameraVitals?.spo2Estimate ?? 0,
    },
    queueStatus:
      entry.seen_at !== null ? 'completed' : entry.state === 'ready' ? 'waiting' : 'in_consultation',
    arrivalTime: entry.arrived_at,
    intakeData: data,
  };
}
