"""N8N-RETIRE-A: the "Bot replies sent by" switch.

`system_settings.chatbot_reply_sender_mode` (`n8n` | `contacts` | `all`, default `n8n`) and
`chatbot_reply_sender_contacts` (respond.io contact ids, for `contacts`) decide whether the CRM
sends a covered contact's bot reply itself instead of handing it to the n8n sender.

Additive only and idempotent (`IF NOT EXISTS`). Default `n8n` keeps every install as it was.

Plan: documentation/plans/chatbot/PLAN-n8n-retire-a-bot-reply-12nov.md.

Revision ID: n8nra_0001_reply_sender
Revises: pc_0001_product_costing
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "n8nra_0001_reply_sender"
down_revision = "pc_0001_product_costing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_reply_sender_mode "
        "VARCHAR(16) NOT NULL DEFAULT 'n8n'"
    )
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_reply_sender_contacts TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_reply_sender_contacts")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_reply_sender_mode")
