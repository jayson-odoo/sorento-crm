"""products.variant_link_manual - manual variant-curation flag (sticky override).

When true, ``reconcile_variant_links`` / ``_adopt_orphans`` / the backfill must
NOT re-derive or re-point that row's variant link. The partial index keeps the
"skip manual" scans cheap on a large products table.

Revision ID: 268_variant_link_manual
Revises: 264_drop_stale_rr_cursor_unique
"""
from alembic import op
import sqlalchemy as sa


revision = "268_variant_link_manual"
down_revision = "264_drop_stale_rr_cursor_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "variant_link_manual",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Partial index - manual rows are the set reconcile/backfill must skip; keeps
    # the "skip manual" scans cheap on a large products table.
    op.create_index(
        "ix_products_variant_link_manual",
        "products",
        ["variant_link_manual"],
        postgresql_where=sa.text("variant_link_manual = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_products_variant_link_manual", table_name="products")
    op.drop_column("products", "variant_link_manual")
