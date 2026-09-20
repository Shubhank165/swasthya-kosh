export interface PatientRef {
  type: 'guest' | 'phone' | 'hospital_id';
  value: string | null;
}

export interface Turn {
  turn_id: number;
  question_id: string;
  transcript: string | null;
  bound_field: string;
  resolved: boolean;
  asr_confidence?: number | null;
  rms?: number | null;
}

export interface FieldValue {
  kind: 'duration' | 'text' | 'boolean' | 'scale' | 'coded' | 'quantity';
  magnitude?: number;
  unit?: string;
  text?: string;
  value?: boolean | number;
  code?: string;
  system?: string | null;
  display?: string | null;
  minimum?: number;
  maximum?: number;
}

export interface FieldItem {
  status: 'answered' | 'unresolved' | 'not_applicable';
  value?: FieldValue;
  original_text?: string;
  language?: string;
  source_turn?: number;
  confidence?: number;
}

export interface IntakeData {
  schema_version: string;
  intake_id: string;
  kiosk_id: string | null;
  hospital_id: string;
  status: string;
  language: string;
  reporter: string;
  department_code: string | null;
  patient_ref: PatientRef;
  engine_version: string | null;
  content_version: string;
  source?: 'kiosk' | 'app';
  app_version?: string;
  turns: Turn[];
  fields: Record<string, FieldItem>;
  red_flags: string[];
  /**
   * Scans the patient attached to this visit.
   *
   * Separate from `fields` because a document and a fact are different things:
   * the OCR of a prescription becomes facts (`current_medications`, `lab_*`),
   * but the scan itself is evidence a physician may want to look at, and it
   * exists even while its reading is still pending or has failed. An empty
   * list and an absent list mean the same thing here — nothing was attached.
   */
  documents?: Array<{
    document_id: string;
    kind: string;
    status?: string;
    captured_at?: string | null;
    items?: Array<{ label?: string; value?: string; text?: string }>;
  }>;

  // Clinical enriched extensions for the Doctor's Dashboard:
  abhaDetails?: {
    abhaNumber: string;
    abhaAddress: string;
    verified: boolean;
    name: string;
    gender: string;
    dob: string;
    photoUrl?: string;
    linkedHealthRecords: number;
  };
  cameraVitals?: {
    heartRateBpm: number;
    respiratoryRateBpm: number;
    confidence: number;
    sensorType: string;
    extractionDurationSec: number;
    timestamp: string;
    spo2Estimate?: number;
    hrvMs?: number;
    qualityIndex: 'Good' | 'Fair' | 'Poor';
  };
}

export interface DoctorNote {
  provisionalDiagnosis: string;
  clinicalNotes: string;
  prescriptions: Array<{
    name: string;
    dosage: string;
    timing: string;
    duration: string;
  }>;
  orderedLabs: string[];
  followUp: string;
}

export interface PatientQueueItem {
  id: string;
  tokenNumber: string;
  name: string;
  age: number;
  gender: string;
  source: 'kiosk' | 'app';
  kioskId?: string;
  abhaNumber: string;
  abhaVerified: boolean;
  chiefComplaint: string;
  severity: number;
  vitalsSummary: {
    hr: number;
    rr: number;
    spo2: number;
  };
  queueStatus: 'waiting' | 'in_consultation' | 'completed';
  arrivalTime: string;
  intakeData: IntakeData;
}

