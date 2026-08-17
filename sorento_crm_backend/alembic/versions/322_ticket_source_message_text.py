"""Conversation intervention tickets: persist the trigger message's own text.

`source_message_id` (migration 321) gave a ticket its identity; this adds the
enquiry TEXT itself so the worklist snippet and the drawer's quoted header can
read it back verbatim instead of re-fetching from Respond.io on every render.
Nullable, additive - no backfill (the original text is not recoverable for
tickets created before this column existed).

Revision ID: 322_ticket_source_message_text
Revises: 321_ticket_source_message_id
Create Date: 2026-08-12
"""
from alembic import op
from sqlalchemy import text


revision = "322_ticket_source_message_text"
down_revision = "321_ticket_source_message_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE conversation_sla_tracking "
            "ADD COLUMN IF NOT EXISTS source_message_text TEXT"
        )
    )


def downgrade() -> None:
    op.execute(
        text("ALTER TABLE conversation_sla_tracking DROP COLUMN IF EXISTS source_message_text")
    )
