"""embedding_queue: pending-only poll and dedupe indexes, prune task (EMBED-QUEUE-DEDUPE).

``documentation/plans/chatbot/PLAN-embed-queue-dedupe-27oct.md``. The embedding poll sorted
every pending row of a 2.5 GB table on each run; these two partial indexes hold only pending
rows:

- ``ix_embedding_queue_pending_poll_cov`` answers the poll's pick (priority, then age) with no
  heap visit. Its definition is the one crew measured on a prod clone, under the same name, so
  an index the owner already built by hand on prod is reused when it is valid.
- ``ix_embedding_queue_pending_source`` answers the "is a row already pending for this
  source?" check every enqueue now makes.

Neither is needed for correctness, so a build that cannot finish fast is skipped, not fatal.

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
    # Never a stall (owner, 27 Oct; runbook memory-and-deploy-guards.md, 13 Oct): each build is
    # CONCURRENTLY with a 5s lock wait and a 90s cap, and a build that fails or times out drops
    # its leftover, logs a WARNING and lets the release go on. The hourly embedding_queue_prune
    # task retries a missing index (app/services/embedding_queue_indexes.py).
    from app.services.embedding_queue_indexes import ensure_embedding_queue_indexes

    with op.get_context().autocommit_block():
        ensure_embedding_queue_indexes(op.get_bind())


def downgrade():
    op.get_bind().execute(
        sa.text("DELETE FROM scheduled_tasks WHERE key IN ('embedding_queue_dedupe', 'embedding_queue_prune')")
    )
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        for name in ("ix_embedding_queue_pending_poll_cov", "ix_embedding_queue_pending_source"):
            bind.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
