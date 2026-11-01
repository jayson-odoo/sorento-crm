"""PRICETAG-COMBO: combo description, free items, prices, top-ups and upgrade marker

Revision ID: ptc_0001_combo_fields
Revises: akn_0001_knowledge
Create Date: 2026-11-01 00:00:00.000000

Additive only. `product_combos` gains description, free_items, list_price, sell_price;
`product_combo_parts` gains sell_price, topup_amount and is_upgrade (NOT NULL DEFAULT false).
A blank price means today's summed price, so no existing combo changes.
"""
import sqlalchemy as sa
from alembic import op

revision = "ptc_0001_combo_fields"
down_revision = "akn_0001_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product_combos", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("product_combos", sa.Column("free_items", sa.Text(), nullable=True))
    op.add_column("product_combos", sa.Column("list_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("product_combos", sa.Column("sell_price", sa.Numeric(12, 2), nullable=True))
    op.add_column("product_combo_parts", sa.Column("sell_price", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "product_combo_parts", sa.Column("topup_amount", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "product_combo_parts",
        sa.Column("is_upgrade", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("product_combo_parts", "is_upgrade")
    op.drop_column("product_combo_parts", "topup_amount")
    op.drop_column("product_combo_parts", "sell_price")
    op.drop_column("product_combos", "sell_price")
    op.drop_column("product_combos", "list_price")
    op.drop_column("product_combos", "free_items")
    op.drop_column("product_combos", "description")
