"""scm reorder_run — cached AI overview column (M5 run-level explainer)

Revision ID: 282_scm_run_overview
Revises: 281_ai_config_anthropic_key
Create Date: 2026-07-17

Lazy-cached, LLM-generated run overview (like reorder_recommendation.explanation).
Idempotent.
"""
from alembic import op

revision = "282_scm_run_overview"
down_revision = "281_ai_config_anthropic_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE scm.reorder_run ADD COLUMN IF NOT EXISTS overview TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE scm.reorder_run DROP COLUMN IF EXISTS overview")
