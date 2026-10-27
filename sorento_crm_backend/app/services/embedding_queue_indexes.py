"""Build the pending-only embedding_queue indexes without ever stalling live work (EMBED-QUEUE-DEDUPE).

Both indexes speed things up and nothing depends on them for correctness, so a build that
cannot finish quickly is abandoned rather than allowed to hold a release or the chatbot (owner,
27 Oct 2026; the 13 Oct slow-migration stall in documentation/runbooks/memory-and-deploy-guards.md).
Every build is CREATE INDEX CONCURRENTLY under a short lock wait and a bounded statement time;
a failed build drops its INVALID leftover, logs a WARNING, and returns. Without the index the
queue runs at today's speed.

Two callers: migration eqd_0001_pending_idx_prune at deploy, and the hourly
embedding_queue_prune task, which is the retry path: it rebuilds whichever index is missing or
invalid, and is a single catalog read when both are present.
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

logger = logging.getLogger(__name__)

# The same definitions as EmbeddingQueue.__table_args__. ix_embedding_queue_pending_poll_cov is
# crew's measured definition, under the same name, so one built by hand on prod is reused.
EMBEDDING_QUEUE_INDEXES: dict[str, str] = {
    "ix_embedding_queue_pending_poll_cov": (
        "ON embedding_queue ((CASE WHEN source_type = 'mcp_tool' THEN 0 ELSE 1 END), created_at) "
        "INCLUDE (available_at, id) WHERE status = 'pending'"
    ),
    "ix_embedding_queue_pending_source": (
        "ON embedding_queue (source_type, source_id) WHERE status = 'pending'"
    ),
}

# The migration default (app/utils/migration_timeouts.py): never queue behind a live transaction
# for longer than this.
BUILD_LOCK_TIMEOUT = "5s"
# Per index. Both together stay under blue/green's 4-minute health wait
# (scripts/blue_green_deploy.sh HEALTH_WAIT_TICKS), like the 180s migration default.
BUILD_STATEMENT_TIMEOUT = "90s"


def index_valid(connection, name: str):
    """pg_index.indisvalid for the index on embedding_queue (True / False), or None when absent."""
    return connection.execute(
        sa.text(
            # Through the table, not to_regclass(name): an unqualified index name resolves along
            # the search_path, so a same-named index in a later schema would answer for it.
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = 'embedding_queue'::regclass AND c.relname = :name"
        ),
        {"name": name},
    ).scalar()


def ensure_embedding_queue_indexes(
    connection,
    *,
    indexes: dict[str, str] | None = None,
    lock_timeout: str = BUILD_LOCK_TIMEOUT,
    statement_timeout: str = BUILD_STATEMENT_TIMEOUT,
) -> dict[str, str]:
    """Build each index that is missing or INVALID; never raises on a failed build.

    `connection` must be in autocommit (CONCURRENTLY refuses a transaction block). Returns
    {index name: "present" | "built" | "failed"}.
    """
    indexes = EMBEDDING_QUEUE_INDEXES if indexes is None else indexes
    outcome: dict[str, str] = {}
    previous = connection.execute(
        sa.text("SELECT current_setting('lock_timeout'), current_setting('statement_timeout')")
    ).one()
    connection.execute(sa.text(f"SET lock_timeout = '{lock_timeout}'"))
    connection.execute(sa.text(f"SET statement_timeout = '{statement_timeout}'"))
    try:
        for name, definition in indexes.items():
            if index_valid(connection, name) is True:
                outcome[name] = "present"
                continue
            try:
                if index_valid(connection, name) is False:
                    # IF NOT EXISTS would keep an INVALID leftover of an earlier attempt forever.
                    connection.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
                connection.execute(sa.text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} {definition}"))
                if index_valid(connection, name) is not True:
                    raise RuntimeError(f"{name} is INVALID after the build")
                outcome[name] = "built"
            except (DBAPIError, RuntimeError) as exc:
                outcome[name] = "failed"
                logger.warning(
                    "embedding_queue index %s not built (%s); the queue works without it and the "
                    "hourly embedding_queue_prune task retries.",
                    name,
                    str(exc).splitlines()[0],
                )
                try:
                    connection.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
                except DBAPIError as drop_exc:
                    # Left INVALID: the next attempt drops it before it builds.
                    logger.warning("could not drop the INVALID %s yet: %s", name, str(drop_exc).splitlines()[0])
    finally:
        connection.execute(sa.text("SELECT set_config('lock_timeout', :v, false)"), {"v": previous[0]})
        connection.execute(sa.text("SELECT set_config('statement_timeout', :v, false)"), {"v": previous[1]})
    return outcome
