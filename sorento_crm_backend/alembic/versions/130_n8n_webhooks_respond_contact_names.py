"""N8n webhook URLs on system_settings; first_name/last_name on respond_contacts.

Revision ID: 130_n8n_webhooks_respond_contact_names
Revises: 129_stock_inquiry_inquiry_number
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa


revision = "130_n8n_webhooks_respond_contact_names"
down_revision = "129_stock_inquiry_inquiry_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("n8n_attachment_webhook_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("n8n_crm_chat_outbound_webhook_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "respond_contacts",
        sa.Column("first_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "respond_contacts",
        sa.Column("last_name", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("respond_contacts", "last_name")
    op.drop_column("respond_contacts", "first_name")
    op.drop_column("system_settings", "n8n_crm_chat_outbound_webhook_url")
    op.drop_column("system_settings", "n8n_attachment_webhook_url")
