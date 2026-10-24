"""sales_orders.ship_info, sales_order_lines.line_remark and section_heading

FULFIL-SO-REMARK (AC-2): AutoCount's Shipping Info (customer PO number, or PURCHASE REQUEST /
SPONSORSHIP), the SO line remark (RTF stripped at ingest) and the text-only heading line above a
line. Three nullable columns; the per-SO remark rules read them.

Revision ID: fsr_0001_so_remark_columns
Revises: or_r4b_top_selling_off
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "fsr_0001_so_remark_columns"
down_revision = "or_r4b_top_selling_off"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales_orders", sa.Column("ship_info", sa.String(length=255), nullable=True))
    op.add_column("sales_order_lines", sa.Column("line_remark", sa.Text(), nullable=True))
    op.add_column("sales_order_lines", sa.Column("section_heading", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sales_order_lines", "section_heading")
    op.drop_column("sales_order_lines", "line_remark")
    op.drop_column("sales_orders", "ship_info")
