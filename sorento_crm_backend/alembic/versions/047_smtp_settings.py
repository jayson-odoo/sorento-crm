"""Add SMTP settings columns to system_settings

Revision ID: 047_smtp_settings
Revises: 046_push_subscriptions
Create Date: 2026-02-16

"""
from alembic import op
import sqlalchemy as sa

revision = "047_smtp_settings"
down_revision = "046_push_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("system_settings", sa.Column("smtp_host", sa.String(255), nullable=True))
    op.add_column("system_settings", sa.Column("smtp_port", sa.String(10), nullable=True))
    op.add_column("system_settings", sa.Column("smtp_secure", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("system_settings", sa.Column("smtp_username", sa.String(255), nullable=True))
    op.add_column("system_settings", sa.Column("smtp_password", sa.String(255), nullable=True))
    op.add_column("system_settings", sa.Column("smtp_from", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("system_settings", "smtp_from")
    op.drop_column("system_settings", "smtp_password")
    op.drop_column("system_settings", "smtp_username")
    op.drop_column("system_settings", "smtp_secure")
    op.drop_column("system_settings", "smtp_port")
    op.drop_column("system_settings", "smtp_host")
