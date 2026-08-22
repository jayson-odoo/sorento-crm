"""GIN trigram indexes on the separator-normalized form of the resolver's probe columns.

The Tier-2.5 trigram probes in ``entity_resolver._trgm_lookup`` no longer score
the raw column. n8n strips dashes and whitespace from every token it sends, so a
raw ``similarity()`` compares a stripped query against a column that kept its
hyphen and collapses; both sides are now stripped before comparing.

That moves every ``%`` gate onto an EXPRESSION, which the raw-column indexes from
migration 169 cannot serve - without these the probes fall back to sequential
scans. Migration 169's indexes stay: other tiers (the prefix/substring ILIKE
probes, list-query search) still read the raw columns.

The expression must stay byte-identical to ``entity_resolver._norm_sql``; a test
asserts exactly that, because a divergence silently drops the index rather than
failing.

Indexed columns (only the ones the trigram probes actually touch)
- products: product_code
- orders: order_number, debtor_name, debtor_code
- customers: customer_code, customer_name

Not indexed: promotions.description and the transporters columns - both tables
are two-figure row counts, where a sequential scan is cheaper than the index.

Revision ID: 410_trgm_norm_idx
Revises: 409_oi_row_pool_redirect
Create Date: 2026-08-22
"""

from alembic import op


revision = "410_trgm_norm_idx"
down_revision = "409_oi_row_pool_redirect"
branch_labels = None
depends_on = None


# Mirrors app/services/entity_resolver.py::_norm_sql. Keep the two in lockstep.
def _norm(column: str) -> str:
    return f"lower(regexp_replace({column}, '[-\\s]+', '', 'g'))"


INDEXES = [
    ("idx_products_product_code_norm_trgm", "products", "product_code"),
    ("idx_orders_order_number_norm_trgm", "orders", "order_number"),
    ("idx_orders_debtor_name_norm_trgm", "orders", "debtor_name"),
    ("idx_orders_debtor_code_norm_trgm", "orders", "debtor_code"),
    ("idx_customers_customer_code_norm_trgm", "customers", "customer_code"),
    ("idx_customers_customer_name_norm_trgm", "customers", "customer_name"),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    for idx_name, table, column in INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON {table} USING gin (({_norm(column)}) gin_trgm_ops);"
        )
    for table in sorted({t for _, t, _ in INDEXES}):
        op.execute(f"ANALYZE {table};")


def downgrade() -> None:
    for idx_name, _, _ in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {idx_name};")
