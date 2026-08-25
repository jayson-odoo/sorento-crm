"""respond-close-convo webhook URL on system_settings.

The CRM -> n8n close signal (UAC AC-M3) was wired through the
N8N_CLOSE_CONVO_WEBHOOK_URL env var for the inert launch. Launching it for
real means the operator sets it from the Integrations settings page like the
other n8n webhooks, so it becomes a system_settings column with the env as
fallback.

Revision ID: 420_close_convo_webhook_setting
Revises: 419_merge_stockvis_oi
Create Date: 2026-08-25
"""
from alembic import op
import sqlalchemy as sa


revision = "420_close_convo_webhook_setting"
down_revision = "419_merge_stockvis_oi"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("n8n_close_convo_webhook_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "n8n_close_convo_webhook_url")
