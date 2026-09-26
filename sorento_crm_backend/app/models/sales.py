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
    event,
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
    """A sales team (J13). No parent (not asked for, plan 3.8).

    The leader is one of the team's current agents (owner ruling 26 Sep ~13:25Z, W1): a current
    attribute, not dated history. `trg_sales_teams_leader_is_member` (below) holds it to an open
    membership row of this team, and `team_service` clears it when the leader leaves.
    """

    __tablename__ = "teams"
    __audit_track__ = True
    # `audit_log.entity_type` defaults to the bare table name, and `teams` is core's.
    __audit_entity_type__ = "sales_teams"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid_str)
    name = Column(String(120), nullable=False)
    # Inactive: not offered for new targets (S1); existing targets still show.
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    leader_sales_agent_id = Column(
        UUID(as_uuid=False),
        ForeignKey(
            "sales_agents.id", ondelete="SET NULL", name="fk_sales_teams_leader_sales_agent_id"
        ),
        nullable=True,
    )
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


def leader_rule_ddl(schema: str) -> list[str]:
    """The leader rule, `trg_sales_teams_leader_is_member`: a team's leader has an OPEN
    membership row (`valid_to IS NULL`) in that team (W1).

    A check constraint cannot look at another table, and a foreign key cannot point at a
    partial unique index, so it is a pair of constraint triggers. They are DEFERRED to the
    commit: one save closes the leader's row and clears the leader, in either order.
    One copy, used by migration `sales_0002_team_leader` and by `create_all` below, so the test
    schema and bootstrap_env carry the same rule production does.
    """
    q = f'"{schema}"'
    return [
        f"""
        CREATE OR REPLACE FUNCTION {q}.sales_team_leader_is_member() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        DECLARE
            v_team_id uuid;
            v_leader uuid;
            v_member boolean;
        BEGIN
            IF TG_TABLE_NAME = 'teams' THEN
                v_team_id := NEW.id;
            ELSE
                v_team_id := OLD.sales_team_id;
            END IF;
            EXECUTE format('SELECT leader_sales_agent_id FROM %I.teams WHERE id = $1',
                           TG_TABLE_SCHEMA)
                INTO v_leader USING v_team_id;
            IF v_leader IS NULL THEN
                RETURN NULL;
            END IF;
            -- EXECUTE never sets FOUND, so the answer comes back through INTO.
            EXECUTE format(
                'SELECT EXISTS (SELECT 1 FROM %I.team_members WHERE sales_team_id = $1 '
                'AND sales_agent_id = $2 AND valid_to IS NULL)', TG_TABLE_SCHEMA)
                INTO v_member USING v_team_id, v_leader;
            IF NOT v_member THEN
                RAISE EXCEPTION 'sales team % leader % is not a current member of the team',
                    v_team_id, v_leader
                    USING ERRCODE = 'check_violation',
                          CONSTRAINT = 'trg_sales_teams_leader_is_member';
            END IF;
            RETURN NULL;
        END
        $fn$
        """,
        f"""
        CREATE CONSTRAINT TRIGGER trg_sales_teams_leader_is_member
        AFTER INSERT OR UPDATE OF leader_sales_agent_id ON {q}.teams
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW WHEN (NEW.leader_sales_agent_id IS NOT NULL)
        EXECUTE FUNCTION {q}.sales_team_leader_is_member()
        """,
        f"""
        CREATE CONSTRAINT TRIGGER trg_sales_team_members_leader_is_member
        AFTER UPDATE OR DELETE ON {q}.team_members
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW WHEN (OLD.valid_to IS NULL)
        EXECUTE FUNCTION {q}.sales_team_leader_is_member()
        """,
    ]


def translated_schema(connection, schema: str = SCHEMA) -> str:
    """`schema` as this connection writes it: a scratch schema under `schema_translate_map`."""
    return connection.get_execution_options().get("schema_translate_map", {}).get(schema, schema)


@event.listens_for(SalesTeamMember.__table__, "after_create")
def _create_leader_rule(target, connection, **kw):  # noqa: ANN001
    # `team_members` is created after `teams` (its foreign key), so both tables exist here.
    for statement in leader_rule_ddl(translated_schema(connection)):
        connection.execute(text(statement))
