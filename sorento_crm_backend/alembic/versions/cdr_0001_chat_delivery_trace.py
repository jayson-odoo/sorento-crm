"""CHAT-DELIVERY-RESOLVER - chat_histories.delivery_trace + delivery_error.

The resolver now stores Respond's own `status[]` timeline and the reason a row is
failed / not_sent (lane CHAT-DELIVERY-RESOLVER, 29 Oct 2026). Additive, nullable, no
backfill, no index: both are read per row, never filtered on.

Revision ID: cdr_0001_chat_delivery_trace
Revises: pmt_0001_parser_max_tokens
Create Date: 2026-10-29
"""
from alembic import op
import sqlalchemy as sa

revision = "cdr_0001_chat_delivery_trace"
down_revision = "pmt_0001_parser_max_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    bind.execute(sa.text("ALTER TABLE chat_histories ADD COLUMN IF NOT EXISTS delivery_trace JSONB NULL"))
    bind.execute(
        sa.text("ALTER TABLE chat_histories ADD COLUMN IF NOT EXISTS delivery_error VARCHAR(512) NULL")
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chat_histories DROP COLUMN IF EXISTS delivery_error")
    op.execute("ALTER TABLE chat_histories DROP COLUMN IF EXISTS delivery_trace")
