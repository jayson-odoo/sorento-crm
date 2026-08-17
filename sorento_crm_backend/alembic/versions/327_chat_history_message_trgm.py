"""Trigram index on chat_histories.message for in-thread search (UAC AC-L8).

In-thread search is `message ILIKE '%needle%'` scoped to one contact. The
leading wildcard makes a btree index useless, so without help this is a scan of
every row that contact ever sent - fine at a few hundred rows, not fine on a
table that grows with every WhatsApp turn in the workspace.

`gin_trgm_ops` indexes the 3-grams of the text, which Postgres can use for
`ILIKE '%x%'` (via the pg_trgm operator class) regardless of where the wildcard
sits. The contact filter still uses the existing
`ix_chat_histories_channel_contact_sent_id`; the planner picks whichever is
cheaper, which is the point.

`CREATE EXTENSION IF NOT EXISTS pg_trgm` needs a privileged role. It is guarded
so a restricted environment that already has the extension is unaffected, and
the index creation is skipped (with a warning, not a failure) when the extension
cannot be installed - search still works, just without the index.

Revision ID: 327_chat_history_trgm
Revises: 326_chat_history_dedupe
Create Date: 2026-08-15
"""
import logging

from alembic import op
from sqlalchemy import text

revision = "327_chat_history_trgm"
down_revision = "326_chat_history_dedupe"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_chat_histories_message_trgm"
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    conn = op.get_bind()
    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except Exception as exc:  # noqa: BLE001 - a restricted role must not block the deploy
        logger.warning("pg_trgm unavailable (%s); skipping %s", exc, INDEX_NAME)
        return
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} "
            "ON chat_histories USING gin (message gin_trgm_ops)"
        )
    )


def downgrade() -> None:
    op.get_bind().execute(text(f"DROP INDEX IF EXISTS {INDEX_NAME}"))
    # pg_trgm is left installed: other objects may already depend on it.
