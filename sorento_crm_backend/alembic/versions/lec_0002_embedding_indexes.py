"""embedding indexes: partial HNSW indexes on embedding_chunks for the records-search model

One keep-set index and one per hot filtered source (`app/services/embedding_indexes.py`). Built through the
online helper (`app/utils/online_index.py`): CONCURRENTLY under the repo's migration limits, and a build that
times out or fails logs a WARNING and lets this revision SUCCEED with the index missing;
`scripts/ensure_goods_chain_indexes.py` retries it. `maintenance_work_mem` is raised for the builds (the keep-set
build took 131 s at the default and 34 s at 512MB, against the shared 180 s statement budget).
Downgrade drops them.

Revision ID: lec_0002_embedding_indexes
Revises: lec_0001_embedding_setting
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.services import embedding_indexes
from app.utils import online_index

revision = "lec_0002_embedding_indexes"
down_revision = "lec_0001_embedding_setting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        bind.execute(sa.text("SET maintenance_work_mem = '512MB'"))
        try:
            online_index.ensure_indexes_online(bind, embedding_indexes.MIGRATION_INDEXES)
        finally:
            bind.execute(sa.text("RESET maintenance_work_mem"))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for table, name, _columns in embedding_indexes.MIGRATION_INDEXES:
            qualified = online_index._qualified(table, name)
            op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {qualified}"))
