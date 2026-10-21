"""CLOSED-LISTS-INDEX-MODE: the closed lists switch of the chatbot parser.

`system_settings.chatbot_closed_lists_mode` (`block` | `index`, default `block`) says how a
CLOSED LISTS parser version sees the closed lists: `block` renders every full list into the
system prompt (today), `index` renders each as one fixed pointer line and the per-turn
CLOSED LISTS block carries only what the message's words and the held products match.

Additive only and idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through
`create_all`, can take it in any order. Default `block` keeps every install exactly as it was.

Revision ID: clim_0001_closed_lists_mode
Revises: spec_bare_size_0001
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "clim_0001_closed_lists_mode"
down_revision = "spec_bare_size_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS chatbot_closed_lists_mode "
        "VARCHAR(16) NOT NULL DEFAULT 'block'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS chatbot_closed_lists_mode")
