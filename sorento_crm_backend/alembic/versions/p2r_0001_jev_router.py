"""AGENTIC-P2: the Jev router settings and key slot

* ``system_settings.chatbot_router_enabled`` (false), ``chatbot_router_min_score`` (0.7),
  ``chatbot_agent_daily_turns`` (50; 0 = no cap).
* ``respond_contacts.chatbot_agent_daily_turns`` - the contact's own cap, NULL = the global value.
* ``ai_assistant_configs.jev_api_key_ciphertext`` - the Jev key, encrypted like the other provider keys.

Additive and defaulted; guarded so a re-run is harmless.

Revision ID: p2r_0001_jev_router
Revises: oiac_0001_ack_override
"""
from alembic import op

revision = "p2r_0001_jev_router"
down_revision = "oiac_0001_ack_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_router_enabled boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE system_settings "
        "ADD COLUMN IF NOT EXISTS chatbot_router_min_score double precision NOT NULL DEFAULT 0.7"
    )
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_agent_daily_turns integer NOT NULL DEFAULT 50"
    )
    op.execute("ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS chatbot_agent_daily_turns integer")
    op.execute("ALTER TABLE ai_assistant_configs ADD COLUMN IF NOT EXISTS jev_api_key_ciphertext text")


def downgrade() -> None:
    op.execute("ALTER TABLE ai_assistant_configs DROP COLUMN IF EXISTS jev_api_key_ciphertext")
    op.execute("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS chatbot_agent_daily_turns")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_agent_daily_turns")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_router_min_score")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_router_enabled")
