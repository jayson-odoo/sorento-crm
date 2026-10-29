"""embedding indexes: partial HNSW indexes on embedding_chunks for the records-search model

One keep-set index and one per hot filtered source (`app/services/embedding_indexes.py`). Built
CONCURRENTLY inside an autocommit block so a live table is not locked; IF NOT EXISTS makes a rerun safe.
Downgrade drops them.

Revision ID: lec_0002_embedding_indexes
Revises: lec_0001_embedding_setting
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "lec_0002_embedding_indexes"
down_revision = "lec_0001_embedding_setting"
branch_labels = None
depends_on = None

MODEL = "text-embedding-3-small"


def upgrade() -> None:
    from app.services.embedding_indexes import index_ddl

    with op.get_context().autocommit_block():
        for ddl in index_ddl(MODEL):
            op.execute(sa.text(ddl))


def downgrade() -> None:
    from app.services.embedding_indexes import index_names

    with op.get_context().autocommit_block():
        for name in index_names(MODEL).values():
            op.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"'))
