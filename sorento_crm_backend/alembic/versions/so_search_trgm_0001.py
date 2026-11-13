"""Trigram indexes for the Sales orders list search (SEARCH-CHIPS).

``documentation/plans/ui/PLAN-search-chips-12nov.md``. The multi-value search runs one
``ILIKE ANY`` per column; without ``gin_trgm_ops`` indexes on ``sales_orders`` it seq-scanned
the table. The shared ``products`` / ``customers`` columns are indexed only when no VALID
plain-column trigram index covers them yet (prod may carry migration 169's).

Built like ``il_0002_integration_log_search`` (owner rule, 27 Oct): through
``online_index.ensure_indexes_online``, CREATE INDEX CONCURRENTLY IF NOT EXISTS in an autocommit
block under the repo's migration limits. A build that times out logs a WARNING and this revision
still SUCCEEDS; ``scripts/ensure_goods_chain_indexes.py`` retries the sales_orders ones on the next
backend start. Until they are VALID the search still answers, at the old speed.

Revision ID: so_search_trgm_0001
Revises: acqs_0001_project_ac_write
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.utils import online_index

revision = "so_search_trgm_0001"
down_revision = "acqs_0001_project_ac_write"
branch_labels = None
depends_on = None

#: Shared master-data columns, indexed here only when nothing covers them yet.
SHARED_INDEXES = tuple(
    (table, f"ix_search_trgm_{table}_{column}", f"USING gin ({column} gin_trgm_ops)")
    for table, column in (
        ("products", "product_code"),
        ("products", "product_name"),
        ("customers", "customer_name"),
    )
)


def _column(columns: str) -> str:
    return columns.split("(", 1)[1].split()[0]


def _has_trgm_index(bind, table: str, column: str) -> bool:
    """True when a VALID single-column ``gin_trgm_ops`` index on the plain column exists, any
    name. An expression index (``lower(...)``) does not serve ``column ILIKE ...``, and an
    INVALID one (an interrupted build) is never used, so neither counts."""
    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_index i
            JOIN pg_class t ON t.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_opclass oc ON oc.oid = i.indclass[0]
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = i.indkey[0]
            WHERE n.nspname = current_schema()
              AND t.relname = :table
              AND a.attname = :column
              AND oc.opcname = 'gin_trgm_ops'
              AND i.indnatts = 1
              AND i.indisvalid
            LIMIT 1
            """
        ),
        {"table": table, "column": column},
    ).first()
    return row is not None


def upgrade():
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        wanted = online_index.SALES_ORDER_SEARCH_INDEXES + tuple(
            index for index in SHARED_INDEXES
            if not _has_trgm_index(bind, index[0], _column(index[2]))
        )
        online_index.ensure_indexes_online(bind, wanted)


def downgrade():
    # Only this revision's own indexes; pg_trgm stays, other features use it.
    with op.get_context().autocommit_block():
        for _table, name, _columns in online_index.SALES_ORDER_SEARCH_INDEXES + SHARED_INDEXES:
            op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
