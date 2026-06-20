"""sla per-event per-channel notify toggles

Adds form_sla_configs.notify_on_escalation and per-event x per-channel user
notification toggles. Backfills the whatsapp toggles from the legacy
users.notify_whatsapp so existing opt-ins are preserved.

Revision ID: a1b2c3d4e5f6
Revises: 932195fa2398
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "932195fa2398"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "form_sla_configs",
        sa.Column("notify_on_escalation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("notify_email_on_assignment", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("notify_email_on_escalation", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("notify_whatsapp_on_assignment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("notify_whatsapp_on_escalation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Preserve existing whatsapp opt-ins: legacy notify_whatsapp covered both events.
    op.execute(
        "UPDATE users SET notify_whatsapp_on_assignment = notify_whatsapp, "
        "notify_whatsapp_on_escalation = notify_whatsapp WHERE notify_whatsapp = true"
    )


def downgrade() -> None:
    op.drop_column("users", "notify_whatsapp_on_escalation")
    op.drop_column("users", "notify_whatsapp_on_assignment")
    op.drop_column("users", "notify_email_on_escalation")
    op.drop_column("users", "notify_email_on_assignment")
    op.drop_column("form_sla_configs", "notify_on_escalation")
