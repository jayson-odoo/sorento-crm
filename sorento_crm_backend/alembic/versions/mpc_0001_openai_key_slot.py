"""ai config - dedicated OpenAI API key slot

Revision ID: mpc_0001_openai_key_slot
Revises: pgl_0001_label_reasoning_effort
Create Date: 2026-10-24

Anthropic (281) and Gemini (361) each got their own key column; OpenAI kept
sharing the generic api_key_ciphertext, so the generic column held whichever
provider the assistant row was set to. A contact-level model pick can run on
OpenAI while the assistant row sits on another provider, so OpenAI gets its own
slot and every provider resolves its own key.

Idempotent so it is safe on any environment.
"""
from alembic import op

revision = "mpc_0001_openai_key_slot"
down_revision = "pgl_0001_label_reasoning_effort"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ai_assistant_configs "
        "ADD COLUMN IF NOT EXISTS openai_api_key_ciphertext TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ai_assistant_configs "
        "DROP COLUMN IF EXISTS openai_api_key_ciphertext"
    )
