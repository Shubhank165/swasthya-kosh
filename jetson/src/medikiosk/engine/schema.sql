-- =============================================================================
-- MediKiosk – Zero-VRAM SQLite Schema  v1.0.0
-- =============================================================================
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA temp_store    = MEMORY;

-- ---------------------------------------------------------------------------
-- 1. NODES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nodes (
    node_id         TEXT PRIMARY KEY,
    prompt_text     TEXT NOT NULL,
    help_text       TEXT,
    ui_type         TEXT NOT NULL,
    ui_options      TEXT,
    ui_min          REAL,
    ui_max          REAL,
    phase           INTEGER NOT NULL,
    framework       TEXT NOT NULL,
    system_tag      TEXT,
    is_red_flag     INTEGER DEFAULT 0,
    is_mandatory    INTEGER DEFAULT 0,
    display_order   INTEGER DEFAULT 999,
    fhir_loinc      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- 2. SYNDROMES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS syndromes (
    syndrome_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    icd10           TEXT,
    category        TEXT,
    severity_tier   INTEGER DEFAULT 2,
    common_frameworks TEXT,
    description     TEXT
);

-- ---------------------------------------------------------------------------
-- 3. MATRIX_WEIGHTS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matrix_weights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    syndrome_id     TEXT NOT NULL REFERENCES syndromes(syndrome_id) ON DELETE CASCADE,
    frequency       INTEGER NOT NULL CHECK (frequency BETWEEN 1 AND 5),
    evoking_strength INTEGER NOT NULL CHECK (evoking_strength BETWEEN 1 AND 5),
    answer_direction TEXT DEFAULT 'POSITIVE',
    notes           TEXT,
    UNIQUE (node_id, syndrome_id, answer_direction)
);

-- ---------------------------------------------------------------------------
-- 4. ROUTING_RULES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routing_rules (
    rule_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_keyword TEXT NOT NULL,
    framework       TEXT NOT NULL,
    priority        INTEGER DEFAULT 10,
    notes           TEXT
);

-- ---------------------------------------------------------------------------
-- 5. NODE_FOLLOWUPS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS node_followups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    trigger_value   TEXT NOT NULL,
    followup_node_id TEXT NOT NULL REFERENCES nodes(node_id) ON DELETE CASCADE,
    priority        INTEGER DEFAULT 10
);

-- ---------------------------------------------------------------------------
-- 6. PROXY_MAPPINGS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proxy_mappings (
    proxy_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    vague_term      TEXT NOT NULL UNIQUE,
    fhir_proxy_tag  TEXT NOT NULL,
    icd10_approx    TEXT,
    clarification_node_id TEXT REFERENCES nodes(node_id)
);

-- ---------------------------------------------------------------------------
-- 7. PATIENT_SESSIONS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patient_sessions (
    session_id      TEXT PRIMARY KEY,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    patient_token   TEXT,
    chief_complaint TEXT,
    framework       TEXT,
    fsm_state       TEXT DEFAULT 'INIT',
    triage_status   TEXT DEFAULT 'ROUTINE',
    questions_asked INTEGER DEFAULT 0,
    state_json      TEXT DEFAULT '{}',
    proxy_history   TEXT DEFAULT '[]',
    top_syndromes   TEXT DEFAULT '[]',
    completed       INTEGER DEFAULT 0,
    completed_at    TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_matrix_node      ON matrix_weights(node_id);
CREATE INDEX IF NOT EXISTS idx_matrix_syndrome  ON matrix_weights(syndrome_id);
CREATE INDEX IF NOT EXISTS idx_routing_kw       ON routing_rules(complaint_keyword);
CREATE INDEX IF NOT EXISTS idx_session_token    ON patient_sessions(patient_token);
CREATE INDEX IF NOT EXISTS idx_followup_trigger ON node_followups(trigger_node_id);

-- Views
CREATE VIEW IF NOT EXISTS v_session_summary AS
SELECT
    session_id, chief_complaint, framework, triage_status,
    questions_asked, top_syndromes, proxy_history, completed,
    created_at, completed_at
FROM patient_sessions;

CREATE VIEW IF NOT EXISTS v_matrix_strength AS
SELECT
    mw.node_id, mw.syndrome_id, mw.frequency, mw.evoking_strength,
    (mw.frequency * mw.evoking_strength) AS strength_product,
    mw.answer_direction, n.ui_type, n.framework, n.phase
FROM matrix_weights mw
JOIN nodes n ON n.node_id = mw.node_id;
