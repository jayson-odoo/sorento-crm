"""Sales module, S2 fix round 2: a unit price on every opportunity line.

The owner's hand test of 27 Sep (PR #1296, F7): a product line had no price. A line now
carries `unit_price`, nullable (a product with no list price stays unpriced), defaulting at
write time to the product's list price, the price the dealer flyer prints.

Downgrade drops the column.

Revision ID: sales_0005_opp_line_price
Revises: sales_0003_opportunities
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op

from app.models.sales import translated_schema

revision = "sales_0005_opp_line_price"
down_revision = "sales_0003_opportunities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = translated_schema(op.get_bind())
    op.add_column(
        "opportunity_lines", sa.Column("unit_price", sa.Numeric(15, 2), nullable=True), schema=schema
    )
    op.create_check_constraint(
        "ck_sales_opportunity_lines_unit_price_nonneg",
        "opportunity_lines",
        "unit_price IS NULL OR unit_price >= 0",
        schema=schema,
    )


def downgrade() -> None:
    schema = translated_schema(op.get_bind())
    op.drop_constraint(
        "ck_sales_opportunity_lines_unit_price_nonneg", "opportunity_lines", schema=schema, type_="check"
    )
    op.drop_column("opportunity_lines", "unit_price", schema=schema)
