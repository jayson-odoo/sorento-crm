"""Conversation intervention tickets: scope ticket identity by (contact, message).

FINDING 6 (code review of feat/conversation-intervention-tickets): migration
321's partial unique index on `source_message_id` alone has no contact scope.
WhatsApp message ids are not guaranteed globally unique across different
contacts/threads, so two DIFFERENT contacts whose trigger messages happen to
share an id collide at the database level - and the application-level
idempotency lookup in `create_tracking` had the identical bug (fixed in the
same change that adds this migration), returning contact A's open ticket as
"already_active" to contact B's create call.

A ticket's identity is really the pair (contact, trigger message), not the
message alone. Swap the index to `(respond_contact_id, source_message_id)`,
scoped exactly as migration 321 (open + conversation-scope rows only) so
form-SLA rows remain untouched.

This is a pure relaxation of migration 321's constraint (adds a column to the
index key), so it can never fail to create on live data: anything the old
index allowed, the new one still allows, plus same-message-different-contact
combinations the old one wrongly forbade.

Revision ID: 323_ticket_source_message_contact_scope
Revises: 322_ticket_source_message_text
Create Date: 2026-08-13
"""
from alembic import op
from sqlalchemy import text


revision = "323_ticket_source_message_contact_scope"
down_revision = "322_ticket_source_message_text"
branch_labels = None
depends_on = None

OLD_INDEX = "uq_conversation_sla_tracking_open_source_message"
NEW_INDEX = "uq_conversation_sla_tracking_open_contact_source_message"

# The conversation family, matching migration 180/321's predicate (form rows excluded).
CONVERSATION_SCOPE = "(source_entity_type IS NULL OR source_entity_type = 'conversation')"


def upgrade() -> None:
    op.execute(text(f"DROP INDEX IF EXISTS {OLD_INDEX}"))
    op.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX}
            ON conversation_sla_tracking (respond_contact_id, source_message_id)
            WHERE source_message_id IS NOT NULL
              AND is_resolved = false
              AND {CONVERSATION_SCOPE}
            """
        )
    )


def downgrade() -> None:
    op.execute(text(f"DROP INDEX IF EXISTS {NEW_INDEX}"))
    op.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {OLD_INDEX}
            ON conversation_sla_tracking (source_message_id)
            WHERE source_message_id IS NOT NULL
              AND is_resolved = false
              AND {CONVERSATION_SCOPE}
            """
        )
    )
