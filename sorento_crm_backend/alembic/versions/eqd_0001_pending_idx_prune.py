"""embedding_queue: pending-only poll and dedupe indexes, prune task (EMBED-QUEUE-DEDUPE).

``documentation/plans/chatbot/PLAN-embed-queue-dedupe-27oct.md``. The embedding poll sorted
every pending row of a 2.5 GB table on each run; these two partial indexes hold only pending
rows:

- ``ix_embedding_queue_pending_poll_cov`` answers the poll's pick (priority, then age) with no
  heap visit. Its definition is the one crew measured on a prod clone, under the same name, so
  an index the owner already built by hand on prod is reused when it is valid.
- ``ix_embedding_queue_pending_source`` answers the "is a row already pending for this
  source?" check every enqueue now makes.

Also seeds two scheduled tasks; no queue row is changed here (owner, 27 Oct: the ~1.17M
duplicate backlog is too heavy for a deploy, about 8 GB of WAL):

- ``embedding_queue_dedupe`` (every 5 min) retires duplicate pending rows in bounded batches,
  keeping the newest per source, and is a no-op once the backlog is gone.
- ``embedding_queue_prune`` (hourly) deletes completed/skipped rows past the retention window.

Revision ID: eqd_0001_pending_idx_prune
Revises: eem_0001_span_pass
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "eqd_0001_pending_idx_prune"
down_revision = "eem_0001_span_pass"
branch_labels = None
depends_on = None

INDEX_LOCK_TIMEOUT = "30s"

INDEXES = {
    "ix_embedding_queue_pending_poll_cov": (
        "ON embedding_queue ((CASE WHEN source_type = 'mcp_tool' THEN 0 ELSE 1 END), created_at) "
        "INCLUDE (available_at, id) WHERE status = 'pending'"
    ),
    "ix_embedding_queue_pending_source": (
        "ON embedding_queue (source_type, source_id) WHERE status = 'pending'"
    ),
}


def _index_valid(bind, name):
    """pg_index.indisvalid for the index (True / False), or None when there is none."""
    return bind.execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = 'embedding_queue'::regclass AND c.relname = :name"
        ),
        {"name": name},
    ).scalar()


def _ensure_index(bind, name, definition):
    """Build the index unless a VALID one exists; drop an INVALID leftover of a failed
    CONCURRENTLY build first, which IF NOT EXISTS would otherwise keep forever."""
    if _index_valid(bind, name) is True:
        return
    if _index_valid(bind, name) is False:
        bind.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
    bind.execute(sa.text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} {definition}"))
    if _index_valid(bind, name) is not True:
        raise RuntimeError(f"eqd_0001_pending_idx_prune: index {name} is INVALID after the build; drop it and rerun.")


TASKS = (
    (
        "embedding_queue_dedupe", "Embedding queue dedupe",
        "Every 5 minutes: marks pending embedding_queue rows skipped when a newer pending row "
        "of the same source covers them, in batches. A no-op once there are none.",
        "minutes", 5,
    ),
    (
        "embedding_queue_prune", "Embedding queue prune",
        "Hourly: deletes completed and skipped embedding_queue rows older than "
        "EMBEDDING_QUEUE_RETENTION_DAYS (default 14), in small batches.",
        "hours", 1,
    ),
)


def upgrade():
    for key, name, description, unit, value in TASKS:
        op.get_bind().execute(
            sa.text(
                """
                INSERT INTO scheduled_tasks
                    (id, key, name, description, enabled, interval_unit, interval_value, timezone)
                VALUES (gen_random_uuid(), :key, :name, :description, true, :unit, :value, 'UTC')
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"key": key, "name": name, "description": description, "unit": unit, "value": value},
        )
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction: the live colour's API and
    # worker keep writing embedding_queue while it builds.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        # Bound the wait for open transactions so a release fails instead of hanging; the
        # INVALID index a timeout leaves is dropped and rebuilt by the next run.
        previous = bind.execute(sa.text("SELECT current_setting('lock_timeout')")).scalar()
        bind.execute(sa.text(f"SET lock_timeout = '{INDEX_LOCK_TIMEOUT}'"))
        try:
            for name, definition in INDEXES.items():
                _ensure_index(bind, name, definition)
        finally:
            bind.execute(sa.text("SELECT set_config('lock_timeout', :v, false)"), {"v": previous})


def downgrade():
    op.get_bind().execute(
        sa.text("DELETE FROM scheduled_tasks WHERE key IN ('embedding_queue_dedupe', 'embedding_queue_prune')")
    )
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        for name in INDEXES:
            bind.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
