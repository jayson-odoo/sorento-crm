"""Tickets — internal Jira-style ticketing.

Status workflow: ``draft -> submitted -> assigned -> responded -> resolved``.
``__audit_track__`` is on so every field change auto-writes an ``audit_logs`` row.
The Activities feed for a ticket is sourced from the generic ``activity_events``
table (entity_type='ticket') — not a per-module comment table.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


TICKET_STATUSES: tuple[str, ...] = ("draft", "submitted", "assigned", "responded", "resolved")
TICKET_PRIORITIES: tuple[str, ...] = ("low", "medium", "high", "urgent")
TICKET_CATEGORIES: tuple[str, ...] = ("bug", "feature", "question", "other")


class Ticket(Base):
    __tablename__ = "tickets"
    __audit_track__ = True
    __audit_entity_type__ = "ticket"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_number = Column(Text, nullable=True, unique=True)

    title = Column(Text, nullable=False)
    description_html = Column(Text, nullable=True)
    description_text = Column(Text, nullable=True)

    status = Column(String(50), nullable=False, default="draft")
    priority = Column(String(20), nullable=False, default="medium")
    category = Column(String(40), nullable=False, default="question")
    due_date = Column(Date, nullable=True)

    raised_by = Column(UUID(as_uuid=False), nullable=False)
    assigned_to = Column(UUID(as_uuid=False), nullable=True)

    # Response payload (rich text on the ticket itself, distinct from the activity feed).
    response_html = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    responded_by = Column(UUID(as_uuid=False), nullable=True)

    # Resolution payload.
    resolution_html = Column(Text, nullable=True)
    resolution_text = Column(Text, nullable=True)
    resolved_by = Column(UUID(as_uuid=False), nullable=True)

    # SLA timestamps.
    submitted_at = Column(DateTime(timezone=False), nullable=True)
    assigned_at = Column(DateTime(timezone=False), nullable=True)
    first_response_at = Column(DateTime(timezone=False), nullable=True)
    responded_at = Column(DateTime(timezone=False), nullable=True)
    resolved_at = Column(DateTime(timezone=False), nullable=True)
    sla_response_due_at = Column(DateTime(timezone=False), nullable=True)
    sla_resolution_due_at = Column(DateTime(timezone=False), nullable=True)
    response_time_hours = Column(Numeric(10, 2), nullable=True)
    resolution_time_hours = Column(Numeric(10, 2), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_assigned_to", "assigned_to"),
        Index("ix_tickets_raised_by", "raised_by"),
        Index("ix_tickets_priority", "priority"),
        Index("ix_tickets_due_date", "due_date"),
        Index("ix_tickets_sla_response_due_at", "sla_response_due_at"),
    )


class TicketWatcher(Base):
    __tablename__ = "ticket_watchers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(
        UUID(as_uuid=False),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=False), nullable=False)
    added_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    added_by = Column(UUID(as_uuid=False), nullable=True)

    __table_args__ = (
        UniqueConstraint("ticket_id", "user_id", name="uq_ticket_watcher_unique"),
        Index("ix_ticket_watchers_ticket", "ticket_id"),
        Index("ix_ticket_watchers_user", "user_id"),
    )


class TicketRespondContactLink(Base):
    """Map a ticket to one or more Respond.io contacts so the Messages tab knows
    which conversation to load. Submitter's contact is auto-linked as primary
    when a phone-number match is found at create-time."""

    __tablename__ = "ticket_respond_contact_links"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(
        UUID(as_uuid=False),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    respond_contact_id = Column(Text, nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=False), nullable=True)

    __table_args__ = (
        UniqueConstraint("ticket_id", "respond_contact_id", name="uq_ticket_respond_contact"),
        Index("ix_ticket_respond_contacts_ticket", "ticket_id"),
    )
