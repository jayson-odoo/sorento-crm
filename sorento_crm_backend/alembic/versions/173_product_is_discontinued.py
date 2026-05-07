"""Add is_discontinued boolean to products.

Auto-derived: True when product.description starts with `****`. Initial backfill
runs the same rule against existing rows.

Revision ID: 173_product_is_discontinued
Revises: 172_complaint_rejection_fields
Create Date: 2026-05-07
"""

import sqlalchemy as sa
from alembic import op


revision = "173_product_is_discontinued"
down_revision = "172_complaint_rejection_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "is_discontinued",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        "UPDATE products SET is_discontinued = TRUE "
        "WHERE description IS NOT NULL "
        "AND LTRIM(description) LIKE '****%'"
    )


def downgrade() -> None:
    op.drop_column("products", "is_discontinued")
