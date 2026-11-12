"""Trigram indexes for the Sales orders list search (SEARCH-CHIPS).

``documentation/plans/ui/PLAN-search-chips-12nov.md``. The multi-value search runs one
``ILIKE ANY`` per column; without ``gin_trgm_ops`` indexes on ``sales_orders`` it seq-scanned
the table. The shared ``products`` / ``customers`` columns are indexed only when no plain-column
trigram index covers them yet (prod may carry migration 169's). Built CONCURRENTLY, so writes
keep going while the indexes build.

Revision ID: so_search_trgm_0001
Revises: il_0002_integration_log_search
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "so_search_trgm_0001"
down_revision = "il_0002_integration_log_search"
branch_labels = None
depends_on = None

PREFIX = "ix_search_trgm_"

SALES_ORDER_COLUMNS = [
    ("sales_orders", "so_number"),
    ("sales_orders", "debtor_name"),
    ("sales_orders", "project_label"),
    ("sales_orders", "po_ref"),
    ("sales_orders", "po_ref_key"),
]
SHARED_COLUMNS = [
    ("products", "product_code"),
    ("products", "product_name"),
    ("customers", "customer_name"),
]


def _name(table: str, column: str) -> str:
    return f"{PREFIX}{table}_{column}"


def _has_trgm_index(bind, table: str, column: str) -> bool:
    """True when a single-column ``gin_trgm_ops`` index on the plain column exists, any name.
    An expression index (``lower(...)``) does not serve ``column ILIKE ...``, so it does not count."""
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
            LIMIT 1
            """
        ),
        {"table": table, "column": column},
    ).first()
    return row is not None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    bind = op.get_bind()
    wanted = list(SALES_ORDER_COLUMNS) + [
        (table, column) for table, column in SHARED_COLUMNS
        if not _has_trgm_index(bind, table, column)
    ]
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        for table, column in wanted:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_name(table, column)} "
                f"ON {table} USING gin ({column} gin_trgm_ops)"
            )


def downgrade():
    # Only this revision's own indexes; pg_trgm stays, other features use it.
    with op.get_context().autocommit_block():
        for table, column in SALES_ORDER_COLUMNS + SHARED_COLUMNS:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_name(table, column)}")
