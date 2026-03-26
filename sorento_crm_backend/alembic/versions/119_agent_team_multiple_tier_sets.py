"""Allow multiple tier sets per access agent.

Revision ID: 119_agent_team_multiple_tier_sets
Revises: 118_user_contact_number
Create Date: 2026-03-26
"""

from alembic import op
import sqlalchemy as sa


revision = "119_agent_team_multiple_tier_sets"
down_revision = "118_user_contact_number"
branch_labels = None
depends_on = None


def _drop_unique_constraint_if_exists(table_name: str, constraint_name: str) -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_constraint c
                    JOIN pg_class t ON t.oid = c.conrelid
                    WHERE t.relname = :table_name
                      AND c.conname = :constraint_name
                ) THEN
                    EXECUTE format(
                        'ALTER TABLE %I DROP CONSTRAINT %I',
                        :table_name,
                        :constraint_name
                    );
                END IF;
            END$$;
            """
        ).bindparams(table_name=table_name, constraint_name=constraint_name)
    )


def _drop_index_if_exists(index_name: str) -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_class
                    WHERE relkind = 'i'
                      AND relname = :index_name
                ) THEN
                    EXECUTE format('DROP INDEX %I', :index_name);
                END IF;
            END$$;
            """
        ).bindparams(index_name=index_name)
    )


def upgrade() -> None:
    # Remove old uniqueness rules:
    # - one row per (agent, code)
    # - one tier row per (agent, tier)
    _drop_unique_constraint_if_exists("agent_teams", "uq_agent_teams_agent_code")
    _drop_index_if_exists("uq_agent_teams_agent_code")
    _drop_unique_constraint_if_exists("agent_teams", "uq_agent_teams_agent_tier")
    _drop_index_if_exists("uq_agent_teams_agent_tier")

    # New rules:
    # - legacy non-tier rows: unique (agent, code) when tier IS NULL
    # - tiered rows: unique (agent, code, tier) when tier IS NOT NULL
    op.create_index(
        "uq_agent_teams_agent_code_tier_null",
        "agent_teams",
        ["agent_id", "code"],
        unique=True,
        postgresql_where=sa.text("tier IS NULL"),
    )
    op.create_index(
        "uq_agent_teams_agent_code_tier_not_null",
        "agent_teams",
        ["agent_id", "code", "tier"],
        unique=True,
        postgresql_where=sa.text("tier IS NOT NULL"),
    )


def downgrade() -> None:
    _drop_unique_constraint_if_exists("agent_teams", "uq_agent_teams_agent_code_tier_not_null")
    _drop_index_if_exists("uq_agent_teams_agent_code_tier_not_null")
    _drop_unique_constraint_if_exists("agent_teams", "uq_agent_teams_agent_code_tier_null")
    _drop_index_if_exists("uq_agent_teams_agent_code_tier_null")

    op.create_index(
        "uq_agent_teams_agent_tier",
        "agent_teams",
        ["agent_id", "tier"],
        unique=True,
        postgresql_where=sa.text("tier IS NOT NULL"),
    )
    op.create_index("uq_agent_teams_agent_code", "agent_teams", ["agent_id", "code"], unique=True)
