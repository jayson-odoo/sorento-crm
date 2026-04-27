"""Add products.currency column defaulting to MYR.

Revision ID: 153_products_currency_default_myr
Revises: 152_commercial_activity_consolidated
"""

from alembic import op
import sqlalchemy as sa


revision = "153_products_currency_default_myr"
down_revision = "152_commercial_activity_consolidated"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="MYR",
        ),
    )
    op.execute("UPDATE products SET currency = 'MYR' WHERE currency IS NULL OR currency = ''")


def downgrade() -> None:
    op.drop_column("products", "currency")
