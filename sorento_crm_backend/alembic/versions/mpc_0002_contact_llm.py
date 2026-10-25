"""respond_contacts - per-contact LLM override (provider + model)

Revision ID: mpc_0002_contact_llm
Revises: mpc_0001_openai_key_slot
Create Date: 2026-10-24

MODEL-PER-CONTACT: both nullable, both or neither; read live each turn.
Idempotent so it is safe on any environment.
"""
from alembic import op

revision = "mpc_0002_contact_llm"
down_revision = "mpc_0001_openai_key_slot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE respond_contacts "
        "ADD COLUMN IF NOT EXISTS chatbot_llm_provider VARCHAR(16), "
        "ADD COLUMN IF NOT EXISTS chatbot_llm_model VARCHAR(100)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE respond_contacts "
        "DROP COLUMN IF EXISTS chatbot_llm_provider, "
        "DROP COLUMN IF EXISTS chatbot_llm_model"
    )
