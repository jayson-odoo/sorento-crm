"""Drop the second legacy unique index uq_conversation_sla_tracking_respond_contact_id.

Migration 180 dropped the named constraint, but a second partial-unique index
(`uq_conversation_sla_tracking_respond_contact_id WHERE respond_contact_id IS NOT NULL`)
existed alongside it and still blocks multi-tracker form flows. Drop it here.
The active-conversation partial unique introduced in 180 still enforces the
conversation-only invariant.

Revision ID: 181_drop_legacy_respond_contact_unique_index
Revises: 180_drop_respond_contact_unique
Create Date: 2026-05-09
"""
from alembic import op
from sqlalchemy import text


revision = "181_drop_legacy_respond_contact_unique_index"
down_revision = "180_drop_respond_contact_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text("DROP INDEX IF EXISTS uq_conversation_sla_tracking_respond_contact_id")
    )


def downgrade() -> None:
    op.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_sla_tracking_respond_contact_id
            ON conversation_sla_tracking (respond_contact_id)
            WHERE respond_contact_id IS NOT NULL
            """
        )
    )
