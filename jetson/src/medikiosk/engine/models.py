"""
MediKiosk – Pydantic Request / Response Models
All API contract types defined here.
Author: MediKiosk Engineering Team | Version: 1.0.0
"""

from __future__ import annotations
from pydantic import BaseModel, Field, validator
from typing import Optional, Any, List, Dict
from enum import Enum


class UIType(str, Enum):
    BINARY        = "BINARY"
    SLIDER        = "SLIDER"
    MULTI_SELECT  = "MULTI_SELECT"
    SINGLE_SELECT = "SINGLE_SELECT"
    BODY_MAP      = "BODY_MAP"
    DATE_PICKER   = "DATE_PICKER"
    TIME_PICKER   = "TIME_PICKER"
    TEXT_SHORT    = "TEXT_SHORT"
    DURATION      = "DURATION"
    NUMERIC       = "NUMERIC"


class TriageStatus(str, Enum):
    ROUTINE   = "ROUTINE"
    URGENT    = "URGENT"
    EMERGENCY = "EMERGENCY"


class FSMState(str, Enum):
    INIT          = "INIT"
    TRIAGE_GATE   = "TRIAGE_GATE"
    FRAMEWORK_ROUTE = "FRAMEWORK_ROUTE"
    ENTROPY_LOOP  = "ENTROPY_LOOP"
    PROXY_ELICIT  = "PROXY_ELICIT"
    COMPLETE      = "COMPLETE"
    EMERGENCY     = "EMERGENCY"


# ─────────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    chief_complaint: str = Field(..., min_length=2, max_length=500,
        description="Patient's presenting complaint in plain language")
    age: Optional[int]   = Field(None, ge=0, le=130)
    sex: Optional[str]   = Field(None, pattern="^(M|F|Other)$")
    language: str        = Field("en", description="ISO 639-1 language code")
    patient_token: Optional[str] = Field(None, description="Anonymous patient identifier")


class AnswerRequest(BaseModel):
    node_id: str         = Field(..., description="ID of the node being answered")
    answer: Optional[Any] = Field(None, description="Patient's answer; None = unknown")
    answer_type: str     = Field("DIRECT",
        description="DIRECT | PROXY | SKIP")
    proxy_tag: Optional[str] = Field(None,
        description="FHIR proxy tag if answer_type=PROXY")


# ─────────────────────────────────────────────
# RESPONSE MODELS
# ─────────────────────────────────────────────

class NodeResponse(BaseModel):
    node_id: str
    prompt_text: str
    help_text: Optional[str]
    ui_type: UIType
    ui_options: Optional[List[str]]
    ui_min: Optional[float]
    ui_max: Optional[float]
    framework: str
    phase: int
    system_tag: Optional[str]
    is_red_flag: bool
    questions_asked: int
    questions_remaining: int


class SessionStartResponse(BaseModel):
    session_id: str
    fsm_state: FSMState
    triage_status: TriageStatus
    first_node: NodeResponse
    message: str


class AnswerResponse(BaseModel):
    session_id: str
    fsm_state: FSMState
    triage_status: TriageStatus
    questions_asked: int
    next_node: Optional[NodeResponse] = None
    completed: bool = False
    message: str


class SyndromeSummary(BaseModel):
    syndrome_id: str
    name: str
    icd10: Optional[str]
    category: str
    severity_tier: int
    score: float
    probability: float  # Normalised 0-1


class SessionSummaryResponse(BaseModel):
    session_id: str
    chief_complaint: str
    framework: str
    triage_status: TriageStatus
    fsm_state: FSMState
    questions_asked: int
    top_syndromes: List[SyndromeSummary]
    proxy_history: List[str]
    completed: bool
    created_at: str
    completed_at: Optional[str]


class FHIRReportResponse(BaseModel):
    resourceType: str = "Bundle"
    id: str
    meta: Dict[str, Any]
    entry: List[Dict[str, Any]]
