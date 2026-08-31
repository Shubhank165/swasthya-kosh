"""ORM models.

Imported for their side effect of registering with `Base.metadata`, which is what
Alembic autogenerate reads.
"""

from app.models.base import Base
from app.models.clinical import (
    AuditLogEntry,
    ClinicalFactRecord,
    ConsentArtefact,
    DocumentRecordRow,
    IdempotencyKeyRecord,
    IntakeRecord,
    PatientRecord,
    RedFlagAlertRecord,
    ReportRecord,
    TerminologyConcept,
    TerminologyMapping,
)
from app.models.queue import (
    DepartmentRecord,
    QueueInstanceRecord,
    QueueRecord,
    TicketRecord,
)

__all__ = [
    "AuditLogEntry",
    "Base",
    "ClinicalFactRecord",
    "ConsentArtefact",
    "DepartmentRecord",
    "DocumentRecordRow",
    "IdempotencyKeyRecord",
    "IntakeRecord",
    "PatientRecord",
    "QueueInstanceRecord",
    "QueueRecord",
    "RedFlagAlertRecord",
    "ReportRecord",
    "TerminologyConcept",
    "TerminologyMapping",
    "TicketRecord",
]
