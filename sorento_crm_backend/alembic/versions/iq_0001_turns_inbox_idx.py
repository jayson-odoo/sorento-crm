"""Partial index on chatbot.turns for the inbox sweeper (CHAT-INBOX-QUEUE, IQ-36).

``documentation/plans/chatbot/PLAN-chat-inbox-queue.md``. Every API process sweeps the inbox
every 1.5 s for contacts with `queued` rows or rows a dead process left `processing` /
`delegated`; those are a handful of rows in a table that is never pruned. Partial on exactly
those states, so the sweep reads only them and costs nothing when the queue is empty. Same
build shape as sodv_0001_ol_from_doc_idx: CONCURRENTLY, bounded lock wait, an INVALID leftover
dropped and rebuilt.

Revision ID: iq_0001_turns_inbox_idx
Revises: or_r4b_top_selling_off
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "iq_0001_turns_inbox_idx"
down_revision = "or_r4b_top_selling_off"
branch_labels = None
depends_on = None

INDEX = "ix_chatbot_turns_inbox_open"
INDEX_LOCK_TIMEOUT = "30s"
WHERE = "status IN ('queued', 'processing', 'delegated') AND is_test = false"


def _index_valid(bind):
    """pg_index.indisvalid for the index (True / False), or None when there is none."""
    return bind.execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = 'chatbot.turns'::regclass AND c.relname = :name"
        ),
        {"name": INDEX},
    ).scalar()


def _ensure_index(bind, *, concurrently: bool) -> None:
    if _index_valid(bind) is True:
        return
    c = "CONCURRENTLY" if concurrently else ""
    if _index_valid(bind) is False:
        bind.execute(sa.text(f"DROP INDEX {c} IF EXISTS chatbot.{INDEX}"))
    bind.execute(
        sa.text(f"CREATE INDEX {c} IF NOT EXISTS {INDEX} ON chatbot.turns (contact_respond_id) WHERE {WHERE}")
    )
    if _index_valid(bind) is not True:
        raise RuntimeError(f"iq_0001: index {INDEX} is INVALID after the build; drop it and rerun.")


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        previous = bind.execute(sa.text("SELECT current_setting('lock_timeout')")).scalar()
        bind.execute(sa.text(f"SET lock_timeout = '{INDEX_LOCK_TIMEOUT}'"))
        try:
            _ensure_index(bind, concurrently=True)
        finally:
            bind.execute(sa.text("SELECT set_config('lock_timeout', :v, false)"), {"v": previous})


def downgrade():
    with op.get_context().autocommit_block():
        op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS chatbot.{INDEX}"))
