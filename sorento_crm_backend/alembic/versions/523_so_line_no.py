"""Sales order lines keep AutoCount's own Seq as `line_no` (PLAN-so-lines-autocount
-order.md section 3.1).

One column, `sales_order_lines.line_no INTEGER NULL`. No index: ordering by it is done
in Python per order, never in SQL across orders. Purchase order lines get nothing - no
screen has asked for their own order.

NULL for every existing row until FoundryX re-pushes (section 3.6, owner-driven,
outside this migration): the ingest side upserts by `source_ref`, so a full re-push
writes `line_no` onto the same rows with nothing else changing.

Revision ID: 523_so_line_no
Revises: 522_oi_cancelled_used_confirm
Create Date: 2026-09-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "523_so_line_no"
down_revision = "522_oi_cancelled_used_confirm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales_order_lines",
        sa.Column("line_no", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sales_order_lines", "line_no")
