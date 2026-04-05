"""Add stock inquiry revise webhook URL to system settings.

Revision ID: 131_stock_inquiry_revise_webhook_url
Revises: 130_n8n_webhooks_respond_contact_names
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa


revision = "131_stock_inquiry_revise_webhook_url"
down_revision = "130_n8n_webhooks_respond_contact_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("n8n_stock_inquiry_revise_webhook_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "n8n_stock_inquiry_revise_webhook_url")
