"""Add message_id to conversation_sla_tracking.

Revision ID: 132_conversation_sla_tracking_message_id
Revises: 131_stock_inquiry_revise_webhook_url
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa


revision = "132_conversation_sla_tracking_message_id"
down_revision = "131_stock_inquiry_revise_webhook_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_sla_tracking",
        sa.Column("message_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_sla_tracking", "message_id")
