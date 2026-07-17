"""ai config — dedicated Anthropic API key slot (DB-configurable, for SCM M5 market web search)

Revision ID: 281_ai_config_anthropic_key
Revises: 280_scm_m5_market_research
Create Date: 2026-07-17

The SCM M5 market-research web search uses Anthropic (the assistant/explainer uses
OpenAI). Rather than an env var, the Anthropic key is configured in the DB alongside
the primary key — a second, dedicated column so both providers can be set at once.
Idempotent so it is safe on any environment.
"""
from alembic import op

revision = "281_ai_config_anthropic_key"
down_revision = "280_scm_m5_market_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ai_assistant_configs "
        "ADD COLUMN IF NOT EXISTS anthropic_api_key_ciphertext TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ai_assistant_configs "
        "DROP COLUMN IF EXISTS anthropic_api_key_ciphertext"
    )
