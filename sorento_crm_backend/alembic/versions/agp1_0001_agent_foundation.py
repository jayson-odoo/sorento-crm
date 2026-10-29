"""AGENTIC-P1: the agent foundation (contact switch, budget settings, conversations table)

* ``respond_contacts.chatbot_agent_enabled`` - explicit entry to the read-only agent. NOT NULL
  DEFAULT false.
* ``system_settings.chatbot_agent_max_rounds`` (8), ``chatbot_agent_max_seconds`` (45),
  ``chatbot_agent_max_input_tokens`` (150000), ``chatbot_agent_compact_tokens`` (40000).
* ``chatbot.agent_conversations`` - conversation boundary and running summary.

Additive and defaulted; guarded so a re-run is harmless.

Revision ID: agp1_0001_agent_foundation
Revises: lec_0004_prompt_synonyms
"""
from alembic import op

revision = "agp1_0001_agent_foundation"
down_revision = "lec_0004_prompt_synonyms"
branch_labels = None
depends_on = None

_SETTINGS = (
    ("chatbot_agent_max_rounds", 8),
    ("chatbot_agent_max_seconds", 45),
    ("chatbot_agent_max_input_tokens", 150000),
    ("chatbot_agent_compact_tokens", 40000),
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE respond_contacts "
        "ADD COLUMN IF NOT EXISTS chatbot_agent_enabled boolean NOT NULL DEFAULT false"
    )
    for name, default in _SETTINGS:
        op.execute(
            f"ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS {name} integer NOT NULL DEFAULT {default}"
        )
    op.execute("CREATE SCHEMA IF NOT EXISTS chatbot")
    op.execute(
        "CREATE TABLE IF NOT EXISTS chatbot.agent_conversations ("
        "id uuid PRIMARY KEY, "
        "contact_respond_id varchar(64) NOT NULL, "
        "created_at timestamptz NOT NULL DEFAULT now(), "
        "summary text, "
        "summary_through timestamptz, "
        "summary_tokens integer, "
        "user_id varchar, "
        "grants_hash varchar(64))"
    )
    # The table may already exist from an earlier run of this revision.
    op.execute("ALTER TABLE chatbot.agent_conversations ADD COLUMN IF NOT EXISTS user_id varchar")
    op.execute("ALTER TABLE chatbot.agent_conversations ADD COLUMN IF NOT EXISTS grants_hash varchar(64)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_conversations_contact "
        "ON chatbot.agent_conversations (contact_respond_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chatbot.agent_conversations")
    for name, _ in reversed(_SETTINGS):
        op.execute(f"ALTER TABLE system_settings DROP COLUMN IF EXISTS {name}")
    op.execute("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS chatbot_agent_enabled")
