"""S6 - the Service Job and what it costs.

A Service Job is *someone going to a site to do something about it*. The Complaint is the
case. They are separate entities, and this module deliberately imports NOTHING from
`app.models.complaints`: a model with no foreign key still couples if it reaches for the
class, and the guard in `tests/test_service_jobs_foundation.py` checks both halves.

Read the migration (325) for why each shape is what it is. The four rules in one line each:

- The job points at its source polymorphically and declares no FK to `complaints` (AC-A6).
- A Technician is never a `users` row, which is what keeps the job's clocks off the SLA
  engine (AC-F21).
- `case_cost_lines` (money out) knows nothing about `charge_state` (money in) (AC-M30).
- The waiting columns hold S4a's option VALUES; S6 seeds no second vocabulary.
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
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Technician(Base):
    """Somebody who attends a site. Deliberately NOT a user.

    They are reached on WhatsApp through a portal link, never through a login. That is the
    premise AC-F21 rests on: form SLA resolves assignees through
    `agent_teams -> team_members -> users`, so giving a technician an account would quietly
    put them back inside an engine that is not supposed to schedule them.
    """

    __tablename__ = "technicians"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    phone = Column(String(32), nullable=True)
    # TEXT, matching respond_contacts.id, which is not a uuid. UNIQUE because one contact
    # is one technician - two rows on one contact split their job history in half and
    # nothing detects it.
    respond_contact_id = Column(
        Text, ForeignKey("respond_contacts.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    # employee | contractor. The discovery study shows the role blurring - an outstation
    # technician is often somebody else's staff - so modelling only employees would make
    # the ordinary case unstorable.
    employment_type = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)


class ExternalProvider(Base):
    """A plumber, a contract technician, a courier. One table, a discriminator (AC-M28).

    Not `suppliers`: that carries payment terms, lead times and SPO linkage, and reusing it
    would couple after-sales to procurement for nothing.
    """

    __tablename__ = "external_providers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    provider_type = Column(String(32), nullable=False)
    phone = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class ServiceJob(Base):
    """One visit to one site about one case.

    `source_entity_type` / `source_entity_id` and NO foreign key to `complaints` (ADR-0009,
    AC-A6). Every job today comes from a complaint, which is exactly why the FK is tempting
    and exactly why it is absent: with it, the first job raised from anything else is a
    migration rather than a row.
    """

    __tablename__ = "service_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_number = Column(String(64), nullable=True, unique=True)

    source_entity_type = Column(String(40), nullable=False)
    source_entity_id = Column(UUID(as_uuid=False), nullable=False)

    status_id = Column(
        UUID(as_uuid=False), ForeignKey("statuses.id", ondelete="SET NULL"), nullable=True
    )

    # The Site as REPORTED, copied from the case rather than derived from the customer
    # record - deriving it sends a technician to a shop (AC-B3, AC-M37).
    site_address = Column(Text, nullable=True)
    site_contact_name = Column(Text, nullable=True)
    site_contact_phone = Column(Text, nullable=True)
    site_latitude = Column(Numeric(10, 7), nullable=True)
    site_longitude = Column(Numeric(10, 7), nullable=True)
    site_place_id = Column(String(128), nullable=True)

    scheduled_from = Column(DateTime(timezone=False), nullable=True)
    scheduled_to = Column(DateTime(timezone=False), nullable=True)

    # The job's own clocks. Attend time is confirmed_at -> arrived_at, computed here
    # because the SLA engine cannot resolve a technician who is not a user (AC-F21 to F23).
    proposed_at = Column(DateTime(timezone=False), nullable=True)
    confirmed_at = Column(DateTime(timezone=False), nullable=True)
    # A date alone does not make a job Confirmed (AC-F5). "Service Date: TBA" is a Proposed
    # job wearing a status that stops anybody chasing it.
    customer_agreed_by = Column(Text, nullable=True)
    arrived_at = Column(DateTime(timezone=False), nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)
    verified_at = Column(DateTime(timezone=False), nullable=True)

    diagnosis_root_cause_id = Column(
        UUID(as_uuid=False),
        ForeignKey("complaint_root_causes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Money IN. `case_cost_lines` is money OUT, and neither derives from the other (AC-M30).
    charge_state = Column(String(24), nullable=True)
    charge_amount = Column(Numeric(12, 2), nullable=True)
    charge_accepted_at = Column(DateTime(timezone=False), nullable=True)

    # S4a's vocabulary, read rather than re-seeded. VALUES, never ids: the lookup binding
    # validates bound columns against option values, and an id column fails on first write.
    waiting_on_party = Column(String(150), nullable=True)
    waiting_on_reason = Column(String(150), nullable=True)
    waiting_since = Column(DateTime(timezone=False), nullable=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        # Every read starts "the jobs for this case". Without this it is a sequential scan
        # of every job Sorento has ever done, on the screen CS opens most.
        Index("ix_service_jobs_source", "source_entity_type", "source_entity_id"),
    )


class ServiceJobAssignment(Base):
    """Which technician was sent, and what became of the attempt.

    A rejected attempt is KEPT rather than overwritten (R12). The history is what lets S9
    exclude it from the technician's attend-time metric - a metric that punishes somebody
    for a customer's cancellation is worse than no metric, and the exclusion has to be
    explicit in the query rather than assumed.
    """

    __tablename__ = "service_job_assignments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_job_id = Column(
        UUID(as_uuid=False), ForeignKey("service_jobs.id", ondelete="CASCADE"), nullable=False
    )
    technician_id = Column(
        UUID(as_uuid=False), ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True
    )
    state = Column(String(20), nullable=True)
    assigned_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_service_job_assignments_job", "service_job_id"),)


class CaseCostLine(Base):
    """What a case cost Sorento. Money OUT, and independent of chargeability (AC-M30).

    A warranty job is free to the consumer and still costs a plumber's fee, so nothing here
    references `charge_state` and neither side derives from the other. Each line records
    what it was FOR, because one number per complaint does not answer the costing question
    that produced this requirement (AC-M29).

    Recording needs no approval (AC-M31): it is bookkeeping, reporting surfaces outliers,
    and an approval queue for a RM80 callout would add friction exactly where CS already
    gates the case.
    """

    __tablename__ = "case_cost_lines"

    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_entity_type = Column(String(40), nullable=False)
    source_entity_id = Column(UUID(as_uuid=False), nullable=False)
    external_provider_id = Column(
        UUID(as_uuid=False), ForeignKey("external_providers.id", ondelete="SET NULL"), nullable=True
    )
    # labour | parts | travel
    cost_kind = Column(String(24), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=True)
    incurred_on = Column(Date, nullable=True)
    recorded_by = Column(Text, nullable=True)
    recorded_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_case_cost_lines_source", "source_entity_type", "source_entity_id"),
    )
