"""chat_histories: message_id + result columns for n8n result-set referencing.

- `chat_histories.message_id` — Respond.io message id of the outgoing message,
  so n8n can later reference a specific message (e.g. when the user replies to
  a quoted message) instead of only the latest one.
- `chat_histories.result` — JSONB array of the numbered options the bot sent in
  that message (idx/uuid/label/...), consumed by
  GET /external/conversation-variables/{respond_io_id}?message_id=... which
  injects it as `referenced_result_set` in the response.

Idempotent: IF NOT EXISTS guards so re-runs are no-ops.

Revision ID: 225_chat_history_message_id_result
Revises: 224_portal_slug_device_trust
Create Date: 2026-06-06
"""
from __future__ import annotations

from alembic import op


revision = "225_chat_history_message_id_result"
down_revision = "224_portal_slug_device_trust"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chat_histories ADD COLUMN IF NOT EXISTS message_id VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE chat_histories ADD COLUMN IF NOT EXISTS result JSONB"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_histories_contact_message_id
        ON chat_histories (contact_id, message_id)
        WHERE message_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chat_histories_contact_message_id")
    op.execute("ALTER TABLE chat_histories DROP COLUMN IF EXISTS result")
    op.execute("ALTER TABLE chat_histories DROP COLUMN IF EXISTS message_id")
