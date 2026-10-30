"""AGENTIC-P3: the agent action ledger

* ``chatbot.agent_actions`` - one row per proposal of write steps the agent made for a
  contact's linked user: status, the steps with their before / after, who confirmed and how.

Additive; guarded so a re-run is harmless.

Revision ID: agp3_0001_agent_actions
Revises: agp1_0001_agent_foundation
"""
from alembic import op

revision = "agp3_0001_agent_actions"
down_revision = "agp1_0001_agent_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The `chatbot` schema exists since 472_chatbot_turns (no CREATE SCHEMA: see agp1_0001).
    op.execute(
        "CREATE TABLE IF NOT EXISTS chatbot.agent_actions ("
        "id uuid PRIMARY KEY, "
        "conversation_id uuid NOT NULL, "
        "turn_id uuid NOT NULL, "
        "confirm_turn_id uuid, "
        "contact_respond_id varchar(64) NOT NULL, "
        "user_id varchar NOT NULL, "
        "decided_by_user_id varchar, "
        "status varchar(16) NOT NULL, "
        "steps jsonb NOT NULL DEFAULT '[]'::jsonb, "
        "via varchar(16), "
        "created_at timestamptz NOT NULL DEFAULT now(), "
        "decided_at timestamptz, "
        "finished_at timestamptz)"
    )
    # The table may already exist from an earlier run of this revision.
    op.execute("ALTER TABLE chatbot.agent_actions ADD COLUMN IF NOT EXISTS decided_by_user_id varchar")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_actions_contact "
        "ON chatbot.agent_actions (contact_respond_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chatbot.agent_actions")
