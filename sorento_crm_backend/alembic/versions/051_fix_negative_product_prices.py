"""Fix negative product prices (list_price, cost_price, invoice_price)

Sets negative list_price to 0; negative cost_price and invoice_price to NULL.
Resolves ResponseValidationError when API returns products with negative prices.

Revision ID: 051_fix_negative_prices
Revises: 050_trim_product_code
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa


revision = "051_fix_negative_prices"
down_revision = "050_trim_product_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    # list_price is NOT NULL - set negative to 0
    connection.execute(sa.text("""
        UPDATE products SET list_price = 0 WHERE list_price < 0
    """))

    # cost_price and invoice_price are nullable - set negative to NULL
    connection.execute(sa.text("""
        UPDATE products SET cost_price = NULL WHERE cost_price < 0
    """))
    connection.execute(sa.text("""
        UPDATE products SET invoice_price = NULL WHERE invoice_price < 0
    """))


def downgrade() -> None:
    pass
