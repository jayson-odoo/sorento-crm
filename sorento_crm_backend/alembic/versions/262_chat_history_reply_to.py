"""chat_histories: reply_to_message_id + reply_to_message columns for WhatsApp quote-reply.

When a user quote-replies to an older bot message, respond.io includes a `replyTo`
on the inbound message. n8n now pushes `reply_to_message_id` (the respond.io message
id of the replied-to message) and `reply_to_message` (its text) on incoming rows.

- `chat_histories.reply_to_message_id` - matches the `message_id` of the earlier
  outgoing row that carried the referenced `result` set. Lets the chatbot resolve a
  pick ("5"/"All") against that message's result set instead of only the latest turn.
- `chat_histories.reply_to_message` - the quoted message text (readability/debugging).

Both NULL for normal (non-reply) messages. Index reply_to_message_id for lookups.

Idempotent: IF NOT EXISTS guards so re-runs are no-ops.

Revision ID: 262_chat_history_reply_to
Revises: 261_semantic_parser_prompt
Create Date: 2026-07-05
"""
from __future__ import annotations

from alembic import op


revision = "262_chat_history_reply_to"
down_revision = "261_semantic_parser_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chat_histories ADD COLUMN IF NOT EXISTS reply_to_message_id VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE chat_histories ADD COLUMN IF NOT EXISTS reply_to_message TEXT"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_histories_contact_reply_to
        ON chat_histories (contact_id, reply_to_message_id)
        WHERE reply_to_message_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chat_histories_contact_reply_to")
    op.execute("ALTER TABLE chat_histories DROP COLUMN IF EXISTS reply_to_message")
    op.execute("ALTER TABLE chat_histories DROP COLUMN IF EXISTS reply_to_message_id")
