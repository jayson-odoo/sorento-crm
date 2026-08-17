"""ai config - dedicated Google Gemini API key slot

Revision ID: 361_ai_config_gemini_key
Revises: 360_merge_media_grn_heads
Create Date: 2026-08-15

Gemini joins OpenAI and Anthropic as a selectable provider, and the chatbot
media image lane is expected to run on it. The key gets its own column for the
same reason Anthropic's did (migration 281): the three providers are configured
at once - the assistant on one, the media lane on another - so a single shared
key slot would make picking a provider per lane impossible.

Idempotent so it is safe on any environment.
"""
from alembic import op

revision = "361_ai_config_gemini_key"
down_revision = "360_merge_media_grn_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ai_assistant_configs "
        "ADD COLUMN IF NOT EXISTS gemini_api_key_ciphertext TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ai_assistant_configs "
        "DROP COLUMN IF EXISTS gemini_api_key_ciphertext"
    )
