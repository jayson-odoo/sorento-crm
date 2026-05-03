"""Add pg_trgm extension + GIN trigram indexes for list-query ILIKE search paths.

The list-query advanced_search endpoint runs ``ILIKE '%term%'`` over multiple
text columns to power the DataGrid quick-search box. Without trigram indexes
those filters do sequential scans, which dominate p95 under stress.

Indexed columns
- products: product_code, product_name, description
- orders: order_number, debtor_name, debtor_code
- customers: customer_name, customer_code  (joined via EXISTS in orders search)

Revision ID: 169_trigram_indexes_list_search
Revises: 168_seed_tickets_rbac
Create Date: 2026-05-03
"""

from alembic import op


revision = "169_trigram_indexes_list_search"
# Merges two prior heads: tickets/activities branch (168) and ai_usage_contact_id branch (166).
down_revision = ("168_seed_tickets_rbac", "166_ai_usage_contact_id")
branch_labels = None
depends_on = None


PRODUCT_INDEXES = [
    ("idx_products_product_code_trgm", "products", "product_code"),
    ("idx_products_product_name_trgm", "products", "product_name"),
    ("idx_products_description_trgm",  "products", "description"),
]

ORDER_INDEXES = [
    ("idx_orders_order_number_trgm", "orders", "order_number"),
    ("idx_orders_debtor_name_trgm",  "orders", "debtor_name"),
    ("idx_orders_debtor_code_trgm",  "orders", "debtor_code"),
]

CUSTOMER_INDEXES = [
    ("idx_customers_customer_name_trgm", "customers", "customer_name"),
    ("idx_customers_customer_code_trgm", "customers", "customer_code"),
]

ALL_INDEXES = PRODUCT_INDEXES + ORDER_INDEXES + CUSTOMER_INDEXES


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    for idx_name, table, column in ALL_INDEXES:
        op.execute(
            f'CREATE INDEX IF NOT EXISTS {idx_name} '
            f'ON {table} USING gin ({column} gin_trgm_ops);'
        )
    for table in sorted({t for _, t, _ in ALL_INDEXES}):
        op.execute(f"ANALYZE {table};")


def downgrade() -> None:
    for idx_name, _, _ in ALL_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {idx_name};")
    # Leave pg_trgm extension installed — other features may rely on it.
