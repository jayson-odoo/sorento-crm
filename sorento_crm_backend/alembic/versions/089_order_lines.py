"""Create order_lines table for delivery order detail.

Revision ID: 089_order_lines
Revises: 088_stock_inquiry_approval
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "089_order_lines"
down_revision = "088_stock_inquiry_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(15, 4), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(15, 4), nullable=True),
        sa.Column("discount", sa.Numeric(15, 4), nullable=True, server_default="0"),
        sa.Column("total", sa.Numeric(15, 4), nullable=True),
        sa.Column("tax", sa.Numeric(15, 4), nullable=True),
        sa.Column("total_excluding_tax", sa.Numeric(15, 4), nullable=True),
        sa.Column("total_including_tax", sa.Numeric(15, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"])
    op.create_index("ix_order_lines_product_id", "order_lines", ["product_id"])
    op.create_index("ix_order_lines_warehouse_id", "order_lines", ["warehouse_id"])
    op.create_index(
        "ix_order_lines_order_product_warehouse",
        "order_lines",
        ["order_id", "product_id", "warehouse_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_order_lines_order_product_warehouse", table_name="order_lines")
    op.drop_index("ix_order_lines_warehouse_id", table_name="order_lines")
    op.drop_index("ix_order_lines_product_id", table_name="order_lines")
    op.drop_index("ix_order_lines_order_id", table_name="order_lines")
    op.drop_table("order_lines")
