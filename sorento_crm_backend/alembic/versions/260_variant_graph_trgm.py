"""variant graph self-FK + GIN trigram indexes (suggest-on-miss Wave 1)

Adds ``products.variant_of_id`` (self-referential FK, ondelete SET NULL so
deleting a parent never blocks) + a btree index on it, and the GIN trigram
indexes the resolver's ``_trgm_lookup`` probe needs (products.product_code /
product_name, orders.debtor_name / debtor_code). ``pg_trgm`` is created here
too (idempotent — already installed manually in the target DB). Plain
CREATE INDEX is fully transactional at this catalog size (~11k products);
CONCURRENTLY is not needed. See
``docs/plans/PLAN-suggest-on-miss-variant-graph.md`` §1 + §5.

Revision ID: 260_variant_graph_trgm
Revises: 259_ai_assistant_trace
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "260_variant_graph_trgm"
down_revision = "259_ai_assistant_trace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # pg_trgm extension (idempotent — already installed manually in prod/staging).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # products.variant_of_id self-FK (SET NULL) + btree index.
    product_cols = {c["name"] for c in insp.get_columns("products")}
    if "variant_of_id" not in product_cols:
        op.add_column(
            "products",
            sa.Column("variant_of_id", postgresql.UUID(as_uuid=False), nullable=True),
        )
        op.create_foreign_key(
            "fk_products_variant_of_id",
            "products",
            "products",
            ["variant_of_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_variant_of_id "
        "ON products (variant_of_id)"
    )

    # GIN trigram indexes for the resolver trgm neighbour probes.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_code_trgm "
        "ON products USING gin (product_code gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_products_name_trgm "
        "ON products USING gin (product_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_debtor_name_trgm "
        "ON orders USING gin (debtor_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_debtor_code_trgm "
        "ON orders USING gin (debtor_code gin_trgm_ops)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    op.execute("DROP INDEX IF EXISTS idx_orders_debtor_code_trgm")
    op.execute("DROP INDEX IF EXISTS idx_orders_debtor_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_products_name_trgm")
    op.execute("DROP INDEX IF EXISTS idx_products_code_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_variant_of_id")

    product_cols = {c["name"] for c in insp.get_columns("products")}
    if "variant_of_id" in product_cols:
        op.drop_constraint("fk_products_variant_of_id", "products", type_="foreignkey")
        op.drop_column("products", "variant_of_id")
    # pg_trgm extension is intentionally left installed on downgrade.
