"""Sales module models: sales teams and their dated membership (plan 3.7, 3.8; slice S6).

**Every table here lives in the `sales` Postgres schema** (owner ruling 26 Sep, V3, on the
ADR-0011 precedent): the schema is the module key, so there is no `sales_` prefix inside it.
Foreign keys between module tables are schema-qualified (`sales.teams.id`); foreign keys to
core (`sales_agents`, `companies`) stay unqualified and resolve in `public`. Raw SQL naming one
of these tables must say `sales.teams`, because `public.teams` is the Users & Access table.

Not the core `teams` table (owner ruling 26 Sep 06:09, T1): its members are CRM users, its
hierarchy grants access, and round-robin, SLA and escalation pick from it. Sales agents have no
login.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base
from app.models.base import CompanyScopedMixin

SCHEMA = "sales"


def _uuid_str() -> str:
    return str(uuid.uuid4())


class SalesTeam(CompanyScopedMixin, Base):
    """A sales team (J13). No parent and no leader: neither was asked for (plan 3.8)."""

    __tablename__ = "teams"
    __audit_track__ = True
    # `audit_log.entity_type` defaults to the bare table name, and `teams` is core's.
    __audit_entity_type__ = "sales_teams"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(120), nullable=False)
    # Inactive: not offered for new targets (S1); existing targets still show.
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_sales_teams_company_lower_name",
            "company_id",
            text("lower(name)"),
            unique=True,
        ),
        {"schema": SCHEMA},
    )


class SalesTeamMember(CompanyScopedMixin, Base):
    """One agent's stay in one team, dated (owner ruling 26 Sep 06:09, T2; UAC S6-14).

    An order dated X counts for team T when its agent has a row for T with
    `coalesce(valid_from, -infinity) <= X <= coalesce(valid_to, infinity)`. `valid_from` empty
    means "from the beginning", which is an agent's FIRST team (V1). A move on date D closes
    the old row at D - 1 and opens a new one at D; removing an agent closes the row at today.
    Rows are never deleted by a move or a removal, so past periods keep their figures.

    One open row per agent per company is the partial unique index below. "No two rows of one
    agent overlap" is checked in `team_service`, the only writer; an exclusion constraint
    would need `btree_gist` for one rule (trigger: a second writer of memberships).
    """

    __tablename__ = "team_members"
    __audit_track__ = True
    __audit_entity_type__ = "sales_team_members"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    sales_team_id = Column(
        UUID(as_uuid=False),
        ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sales_agent_id = Column(
        UUID(as_uuid=False),
        ForeignKey("sales_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="ck_sales_team_members_dates",
        ),
        Index(
            "uq_sales_team_members_open",
            "company_id",
            "sales_agent_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        {"schema": SCHEMA},
    )
