"""Allow multiple order lines per product+warehouse via line_sequence.

Revision ID: 135_order_lines_line_sequence_drop_product_wh_uniq
Revises: 134_reapply_warehouse_master_per_loc
Create Date: 2026-04-11

"""
from alembic import op
import sqlalchemy as sa


revision = "135_order_lines_line_sequence_drop_product_wh_uniq"
down_revision = "134_reapply_warehouse_master_per_loc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "order_lines",
        sa.Column("line_sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id AS line_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY order_id ORDER BY created_at ASC NULLS LAST, id ASC
                   ) AS rn
            FROM order_lines
        )
        UPDATE order_lines ol
        SET line_sequence = ranked.rn
        FROM ranked
        WHERE ol.id = ranked.line_id
        """
    )
    op.alter_column("order_lines", "line_sequence", server_default=None)

    op.drop_index("ix_order_lines_order_product_warehouse", table_name="order_lines")
    op.create_index(
        "ix_order_lines_order_product_warehouse",
        "order_lines",
        ["order_id", "product_id", "warehouse_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_order_lines_order_id_line_sequence",
        "order_lines",
        ["order_id", "line_sequence"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_order_lines_order_id_line_sequence", "order_lines", type_="unique")
    op.drop_index("ix_order_lines_order_product_warehouse", table_name="order_lines")
    op.create_index(
        "ix_order_lines_order_product_warehouse",
        "order_lines",
        ["order_id", "product_id", "warehouse_id"],
        unique=True,
    )
    op.drop_column("order_lines", "line_sequence")
