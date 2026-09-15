from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Urgency(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class ClinicalUpdate(BaseModel):
    """Only facts explicitly supported by the latest patient utterance."""

    model_config = ConfigDict(extra="forbid")

    complaint: str | None
    duration: str | None
    onset: str | None
    severity: int | None = Field(ge=0, le=10)
    vomiting: bool | None
    fever: bool | None
    breathlessness: bool | None
    chest_pain: bool | None
    pain_radiation: bool | None
    sweating: bool | None
    active_bleeding: bool | None
    altered_consciousness: bool | None
    one_sided_weakness: bool | None
    speech_difficulty: bool | None
    pregnancy_possible: bool | None
    age_years: int | None = Field(ge=0, le=125)
    medications: list[str]
    allergies: list[str]
    evidence: list[str]


class PatientState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complaint: str | None = None
    duration: str | None = None
    onset: str | None = None
    severity: int | None = Field(default=None, ge=0, le=10)
    vomiting: bool | None = None
    fever: bool | None = None
    breathlessness: bool | None = None
    chest_pain: bool | None = None
    pain_radiation: bool | None = None
    sweating: bool | None = None
    active_bleeding: bool | None = None
    altered_consciousness: bool | None = None
    one_sided_weakness: bool | None = None
    speech_difficulty: bool | None = None
    pregnancy_possible: bool | None = None
    age_years: int | None = Field(default=None, ge=0, le=125)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    original_transcripts: list[str] = Field(default_factory=list)
    detected_language: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def apply(self, update: ClinicalUpdate, transcript: str, language: str | None) -> None:
        scalar_fields = (
            "complaint",
            "duration",
            "onset",
            "severity",
            "vomiting",
            "fever",
            "breathlessness",
            "chest_pain",
            "pain_radiation",
            "sweating",
            "active_bleeding",
            "altered_consciousness",
            "one_sided_weakness",
            "speech_difficulty",
            "pregnancy_possible",
            "age_years",
        )
        for field_name in scalar_fields:
            value = getattr(update, field_name)
            if value is None:
                continue
            if field_name == "complaint" and self.complaint is not None:
                # The chief complaint is what brought the patient in. A symptom named later in the
                # interview is an associated finding, not a replacement for it.
                continue
            setattr(self, field_name, value)

        for field_name in ("medications", "allergies"):
            current = getattr(self, field_name)
            for value in getattr(update, field_name):
                if value and value not in current:
                    current.append(value)

        self.original_transcripts.append(transcript)
        if language:
            self.detected_language = language
        self.updated_at = datetime.now(timezone.utc)


class RedFlagAlert(BaseModel):
    rule_id: str
    urgency: Urgency
    message: str
    evidence: list[str]


class QuestionSpec(BaseModel):
    id: str
    target_field: str
    templates: dict[str, str]

    def template_for(self, language: str | None) -> str:
        """Text for a language code. Accepts 'hi', 'hi-IN', or 'hinglish'; falls back to English."""

        normalized = (language or "en").lower()
        if normalized in {"hinglish", "hi-latn"}:
            normalized = "hi"
        return self.templates.get(normalized[:2], self.templates["en"])


class TurnResult(BaseModel):
    transcript: str
    language: str | None
    state: PatientState
    red_flags: list[RedFlagAlert]
    next_question_id: str | None
    next_question: str | None
    should_alert_staff: bool
    disclaimer: str = "Prototype intake support only. It does not diagnose or replace a clinician."
