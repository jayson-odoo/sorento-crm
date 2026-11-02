"""Create the five integration_log indexes its model declares (INTEGRATION-LOG-INDEXES).

``documentation/plans/infra/PLAN-integration-log-indexes-02nov.md``. Crew, 2 Nov 2026, read-only on
a 20 Oct prod copy: ``integration_log`` (~1.6 GB, ~1.2M rows) carried only its PK and
``uq_integration_log_ideation_status_event``. The five indexes ``app/models/integration.py``
declares were never created by any migration (create_all skips an existing table), so the
upload-activity bell's latest-log query (``app/api/v1/resources/upload_activity.py``, on every
protected page) seq-scanned the whole table: 5-82 s a call, evicting shared buffers for every
other page.

Built like ``gc_idx_0001_spo_from_po_key``: CREATE INDEX CONCURRENTLY IF NOT EXISTS in an
autocommit block, under the repo's migration limits (lock_timeout 5s, one shared 180s statement
budget, ``app/utils/migration_timeouts.py``), so it never blocks the log's writers and never
queues behind a long transaction. A VALID index of the same name is kept (crew already built
the composite by hand on the dev DB); an INVALID leftover is dropped and rebuilt. A build that
times out logs a WARNING and this revision still SUCCEEDS; ``scripts/ensure_goods_chain_indexes.py``
(run in the background by ``start.sh`` on every backend start) retries what is missing. The
composite builds first, so the budget goes to the index the bell needs. All of it lives in
``app/utils/online_index.py`` (INTEGRATION_LOG_INDEXES).

Revision ID: il_0001_integration_log_indexes
Revises: qcp_0001_cover_page_fields
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.utils import online_index

revision = "il_0001_integration_log_indexes"
down_revision = "qcp_0001_cover_page_fields"
branch_labels = None
depends_on = None


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction: n8n callbacks, Respond.io sends
    # and every upload keep writing integration_log while it builds.
    with op.get_context().autocommit_block():
        online_index.ensure_indexes_online(op.get_bind(), online_index.INTEGRATION_LOG_INDEXES)


def downgrade():
    with op.get_context().autocommit_block():
        for _table, name, _columns in online_index.INTEGRATION_LOG_INDEXES:
            op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
