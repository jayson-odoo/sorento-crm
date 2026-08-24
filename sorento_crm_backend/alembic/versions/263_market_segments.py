"""market segments: retail/project routing for CS team members.

Adds a market-segment catalog + two M2M joins (contact ↔ segment, team_member ↔
segment) and a segment_key discriminator on the round-robin cursor so the
next-assignee rotation can be scoped per contact segment.

- market_segments                  - catalog (seed retail, project)
- respond_contact_market_segments  - contact ↔ segment
- team_member_market_segments      - team membership ↔ segment
- agent_team_round_robin_cursors.segment_key VARCHAR(120) NOT NULL DEFAULT ''
  ('' = the legacy / no-segment cursor; unique key widened to include it)

Match semantics live in the service: contact∩member non-empty, untagged member
serves all, untagged/absent contact = no filter.

Idempotent: IF NOT EXISTS guards + ON CONFLICT DO NOTHING seed.

Revision ID: 263_market_segments
Revises: 262_chat_history_reply_to
Create Date: 2026-07-05
"""
from __future__ import annotations

from alembic import op


revision = "263_market_segments"
down_revision = "262_chat_history_reply_to"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- catalog ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_segments (
            code        VARCHAR(50)  PRIMARY KEY,
            name        VARCHAR(255) NOT NULL,
            description TEXT,
            is_active   BOOLEAN      NOT NULL DEFAULT true,
            sort_order  INTEGER,
            created_at  TIMESTAMP    NOT NULL DEFAULT now(),
            updated_at  TIMESTAMP    NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_market_segments_is_active ON market_segments (is_active)"
    )

    # --- contact ↔ segment ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS respond_contact_market_segments (
            contact_id   TEXT        NOT NULL REFERENCES respond_contacts(id) ON DELETE CASCADE,
            segment_code VARCHAR(50) NOT NULL REFERENCES market_segments(code) ON DELETE CASCADE,
            created_at   TIMESTAMP   NOT NULL DEFAULT now(),
            PRIMARY KEY (contact_id, segment_code)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_respond_contact_market_segments_contact_id "
        "ON respond_contact_market_segments (contact_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_respond_contact_market_segments_segment_code "
        "ON respond_contact_market_segments (segment_code)"
    )

    # --- team membership ↔ segment ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS team_member_market_segments (
            team_member_id UUID        NOT NULL REFERENCES team_members(id) ON DELETE CASCADE,
            segment_code   VARCHAR(50) NOT NULL REFERENCES market_segments(code) ON DELETE CASCADE,
            created_at     TIMESTAMP   NOT NULL DEFAULT now(),
            PRIMARY KEY (team_member_id, segment_code)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_member_market_segments_team_member_id "
        "ON team_member_market_segments (team_member_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_member_market_segments_segment_code "
        "ON team_member_market_segments (segment_code)"
    )

    # --- cursor segment_key ---
    op.execute(
        "ALTER TABLE agent_team_round_robin_cursors "
        "ADD COLUMN IF NOT EXISTS segment_key VARCHAR(120) NOT NULL DEFAULT ''"
    )
    # Swap the 2-col unique for a 3-col unique including segment_key.
    op.execute("DROP INDEX IF EXISTS ix_agent_team_round_robin_cursors_agent_team")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_team_rr_cursors_agent_team_segment "
        "ON agent_team_round_robin_cursors (agent_id, team_id, segment_key)"
    )

    # --- seed ---
    op.execute(
        """
        INSERT INTO market_segments (code, name, sort_order) VALUES
            ('retail',  'Retail',  1),
            ('project', 'Project', 2)
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_team_rr_cursors_agent_team_segment")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_team_round_robin_cursors_agent_team "
        "ON agent_team_round_robin_cursors (agent_id, team_id)"
    )
    op.execute("ALTER TABLE agent_team_round_robin_cursors DROP COLUMN IF EXISTS segment_key")
    op.execute("DROP TABLE IF EXISTS team_member_market_segments")
    op.execute("DROP TABLE IF EXISTS respond_contact_market_segments")
    op.execute("DROP TABLE IF EXISTS market_segments")
