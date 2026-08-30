"""Mention email opt-in: users.notify_email_on_mention.

Revision ID: 444_notify_email_on_mention
Revises: 443_fulfilment_planning_flag
Create Date: 2026-08-30

Adds the per-user opt-in for the "someone mentioned me in an internal note"
email. Defaults on, which is also the backfill for every existing row - the
behaviour the feature ships with. Email only: this event has no WhatsApp twin,
so there is no notify_whatsapp_on_mention column.

Idempotent and reversible.
"""
from alembic import op
import sqlalchemy as sa


revision = "444_notify_email_on_mention"
down_revision = "443_fulfilment_planning_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notify_email_on_mention",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_email_on_mention")
