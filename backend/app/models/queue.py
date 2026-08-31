"""Queue persistence.

`Queue` and `QueueInstance` are separate tables for the reason the domain keeps
them separate entities: the consultant on duty changes and a session pauses
without the configured queue being edited.

`tickets` carries no intake state column. Intake state lives on `intakes`, and
the two are joined only where a caller genuinely needs both — which is what
keeps invariant 8 true in the database as well as in the code.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class DepartmentRecord(Base, TimestampMixin):
    """An OPD department — Kayachikitsa, Panchakarma, Shalya Tantra, and so on."""

    __tablename__ = "departments"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    facility: Mapped[str] = mapped_column(String(128), nullable=False)

    queues: Mapped[list[QueueRecord]] = relationship(back_populates="department")


class QueueRecord(Base, TimestampMixin):
    """The durable queue definition. Editing this is an administrative act."""

    __tablename__ = "queues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    department_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("departments.code"), nullable=False, index=True
    )
    service_point: Mapped[str] = mapped_column(String(64), nullable=False)
    assignment_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    #: Weekday numbers (Mon=0). Empty means every day.
    schedule_days: Mapped[list[int]] = mapped_column(JSON, default=list)
    session: Mapped[str] = mapped_column(String(16), nullable=False, default="full_day")
    priority_classes: Mapped[list[str]] = mapped_column(JSON, default=list)
    prefer_intake_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    intake_ready_window: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_overtaken: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    recall_after_tokens: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_recalls: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    unserved_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="carry_forward"
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="source_of_truth")

    department: Mapped[DepartmentRecord] = relationship(back_populates="queues")
    instances: Mapped[list[QueueInstanceRecord]] = relationship(back_populates="queue")


class QueueInstanceRecord(Base, TimestampMixin):
    """Today's run of a queue."""

    __tablename__ = "queue_instances"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    queue_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("queues.id"), nullable=False, index=True
    )
    service_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    session: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    practitioner_id: Mapped[str | None] = mapped_column(String(64), index=True)
    service_point: Mapped[str | None] = mapped_column(String(64))
    #: The token counter. Incremented under the row lock that `issue` takes, so
    #: two counters can never hand out the same number.
    last_issued: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    now_serving: Mapped[str | None] = mapped_column(String(32))
    waiting_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    no_show_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_service_seconds: Mapped[float | None] = mapped_column(Float)
    served_sample: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_into: Mapped[str | None] = mapped_column(String(64))

    queue: Mapped[QueueRecord] = relationship(back_populates="instances")
    tickets: Mapped[list[TicketRecord]] = relationship(back_populates="instance")

    __table_args__ = (
        UniqueConstraint(
            "queue_id", "service_date", "session", name="uq_queue_instances_queue_date_session"
        ),
    )


class TicketRecord(Base, TimestampMixin):
    """One patient's place in one queue."""

    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    queue_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("queues.id"), nullable=False, index=True
    )
    instance_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("queue_instances.id"), nullable=False, index=True
    )
    token_number: Mapped[str] = mapped_column(String(32), nullable=False)
    token_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Effective ordering position; a recalled ticket sits later than its token.
    recall_sequence: Mapped[int | None] = mapped_column(Integer)
    priority_class: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: Hospital-owned. Orthogonal to `intakes.state`.
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    patient_id: Mapped[str | None] = mapped_column(String(64), index=True)
    intake_id: Mapped[str | None] = mapped_column(String(64), index=True)
    appointment_slot_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recall_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: How many times this ticket has been passed by a better-prepared one.
    #: Surfaced on the dashboard and capped, so the preference cannot starve it.
    overtaken_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wait_credit_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    transferred_from: Mapped[str | None] = mapped_column(String(64))
    transferred_to: Mapped[str | None] = mapped_column(String(64))
    cancelled_reason: Mapped[str | None] = mapped_column(Text)
    #: Escalation provenance. All three are set together or none are.
    escalation_alert_id: Mapped[str | None] = mapped_column(String(64))
    escalation_acknowledged_by: Mapped[str | None] = mapped_column(String(64))
    escalation_escalated_by: Mapped[str | None] = mapped_column(String(64))
    escalation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_reason: Mapped[str | None] = mapped_column(Text)

    instance: Mapped[QueueInstanceRecord] = relationship(back_populates="tickets")

    __table_args__ = (
        UniqueConstraint("instance_id", "token_number", name="uq_tickets_instance_token"),
        # The index `call_next` reads under FOR UPDATE SKIP LOCKED.
        Index("ix_tickets_instance_state_priority", "instance_id", "state", "priority_class"),
    )
