"""Trigram index for the Integration Log search box (INTLOG-SPEED-2).

``documentation/plans/infra/PLAN-intlog-search-format-03nov.md``. Crew pass, 12 Nov 2026, on the
dev copy (~1.2M rows): an 8-character Business ID search took 19.5-28 s, because the search was an
OR of seven ``ILIKE '%term%'`` that no index can serve. The search now matches one expression
(``online_index.INTEGRATION_LOG_SEARCH_EXPR``) and this builds a GIN ``gin_trgm_ops`` index on
exactly that expression, so a rare term is an index lookup.

Built like ``il_0001_integration_log_indexes``: CREATE INDEX CONCURRENTLY IF NOT EXISTS in an
autocommit block, under the repo's migration limits, so it never blocks the log's writers. A build
that times out logs a WARNING and this revision still SUCCEEDS; ``scripts/ensure_goods_chain_indexes.py``
(run in the background by ``start.sh`` on every backend start) retries it. Until it is VALID the
search still answers, at the old speed. ``pg_trgm`` is already installed (169_trigram_indexes_list_search);
CREATE EXTENSION IF NOT EXISTS here only covers a database built without that revision.

Revision ID: il_0002_integration_log_search
Revises: pc_0001_product_costing
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.utils import online_index

revision = "il_0002_integration_log_search"
down_revision = "pc_0001_product_costing"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        online_index.ensure_indexes_online(bind, online_index.INTEGRATION_LOG_SEARCH_INDEXES)


def downgrade():
    with op.get_context().autocommit_block():
        for _table, name, _columns in online_index.INTEGRATION_LOG_SEARCH_INDEXES:
            op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
