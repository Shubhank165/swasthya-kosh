"""ORM models.

Imported for their side effect of registering with `Base.metadata`, which is what
Alembic autogenerate reads and what the tenancy test enumerates.
"""

from app.models.base import Base
from app.models.clinical import (
    TENANT_COLUMN,
    TENANT_EXEMPT_TABLES,
    AuditLogEntry,
    ClinicalFactRecord,
    ConsentArtefact,
    DocumentItemRecord,
    DocumentRecordRow,
    HospitalRecord,
    IdempotencyKeyRecord,
    IngestRawRecord,
    IntakeRecord,
    PatientRecord,
    RedFlagEventRecord,
    ReportRecord,
    TerminologyConcept,
    TerminologyMapping,
)

__all__ = [
    "TENANT_COLUMN",
    "TENANT_EXEMPT_TABLES",
    "AuditLogEntry",
    "Base",
    "ClinicalFactRecord",
    "ConsentArtefact",
    "DocumentItemRecord",
    "DocumentRecordRow",
    "HospitalRecord",
    "IdempotencyKeyRecord",
    "IngestRawRecord",
    "IntakeRecord",
    "PatientRecord",
    "RedFlagEventRecord",
    "ReportRecord",
    "TerminologyConcept",
    "TerminologyMapping",
]
