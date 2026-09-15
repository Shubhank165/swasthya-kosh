# MediKiosk – System Configuration & Constants
# =============================================
# All tunable thresholds, version flags, and enum-like constants live here.
# Author : MediKiosk Engineering Team  |  Version: 1.0.0

# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────
# Resolved against this package rather than the working directory: the kiosk is started from
# several different places (systemd, scripts/kiosk, pytest) and a bare relative name silently
# created an empty database in whichever directory happened to be current.
DB_PATH: str = str(__import__("pathlib").Path(__file__).with_name("clinical.db"))

# ─────────────────────────────────────────────
# Engine Limits
# ─────────────────────────────────────────────
MAX_QUESTIONS: int = 12
FLATTENING_THRESHOLD: float = 0.02    # Stop if delta top_prob < 2%
MIN_SYNDROME_SCORE: float   = 0.05    # Syndromes below this are inactive
MIN_ACTIVE_SYNDROMES: int   = 1

# ─────────────────────────────────────────────
# Triage
# ─────────────────────────────────────────────
TRIAGE_PHASE_TAG: str = "TRIAGE"
EMERGENCY_STATUS: str = "EMERGENCY"
URGENT_STATUS: str    = "URGENT"
ROUTINE_STATUS: str   = "ROUTINE"

# ─────────────────────────────────────────────
# Clinical Frameworks
# ─────────────────────────────────────────────
FRAMEWORK_SOCRATES : str = "SOCRATES"
FRAMEWORK_OLD_CARTS: str = "OLD_CARTS"
FRAMEWORK_SAMPLE   : str = "SAMPLE"
FRAMEWORK_COCA     : str = "COCA"
FRAMEWORK_ROTS     : str = "ROTS"

ALL_FRAMEWORKS = [
    FRAMEWORK_SOCRATES,
    FRAMEWORK_OLD_CARTS,
    FRAMEWORK_SAMPLE,
    FRAMEWORK_COCA,
    FRAMEWORK_ROTS,
]

# ─────────────────────────────────────────────
# UI Widget Types
# ─────────────────────────────────────────────
UI_BINARY       = "BINARY"
UI_SLIDER       = "SLIDER"
UI_MULTI_SELECT = "MULTI_SELECT"
UI_SINGLE_SELECT= "SINGLE_SELECT"
UI_BODY_MAP     = "BODY_MAP"
UI_DATE_PICKER  = "DATE_PICKER"
UI_TIME_PICKER  = "TIME_PICKER"
UI_TEXT_SHORT   = "TEXT_SHORT"
UI_DURATION     = "DURATION"
UI_NUMERIC      = "NUMERIC"

# ─────────────────────────────────────────────
# Answer normalisation weights
# ─────────────────────────────────────────────
ANSWER_YES : float =  1.0
ANSWER_NO  : float = -0.5   # Partial exclusion signal
ANSWER_NULL: float =  0.0   # No information - safe zero
SLIDER_MAX : int   = 10

# ─────────────────────────────────────────────
# FSM States
# ─────────────────────────────────────────────
FSM_STATE_INIT         = "INIT"
FSM_STATE_TRIAGE       = "TRIAGE_GATE"
FSM_STATE_FRAMEWORK    = "FRAMEWORK_ROUTE"
FSM_STATE_ENTROPY_LOOP = "ENTROPY_LOOP"
FSM_STATE_PROXY_ELICIT = "PROXY_ELICIT"
FSM_STATE_COMPLETE     = "COMPLETE"
FSM_STATE_EMERGENCY    = "EMERGENCY"

# ─────────────────────────────────────────────
# FHIR Proxy Tags
# ─────────────────────────────────────────────
PROXY_TAGS = {
    "heart_issue"     : "Cardiac_Unspecified",
    "lung_issue"      : "Pulmonary_Unspecified",
    "kidney_issue"    : "Renal_Unspecified",
    "liver_issue"     : "Hepatic_Unspecified",
    "sugar_issue"     : "DM_Unspecified",
    "thyroid_issue"   : "Thyroid_Unspecified",
    "blood_issue"     : "Hematologic_Unspecified",
    "neuro_issue"     : "Neurologic_Unspecified",
    "psych_issue"     : "Psychiatric_Unspecified",
    "bone_issue"      : "Musculoskeletal_Unspecified",
    "allergy_unknown" : "Allergy_Unspecified",
    "cancer_unknown"  : "Malignancy_Unspecified",
    "surgery_unknown" : "Surgery_Unspecified",
}

# ─────────────────────────────────────────────
# API
# ─────────────────────────────────────────────
API_VERSION       = "v1"
API_PREFIX        = f"/api/{API_VERSION}"
SESSION_TTL_HOURS = 8
