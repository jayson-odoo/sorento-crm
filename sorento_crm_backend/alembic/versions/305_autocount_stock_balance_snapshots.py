"""AutoCount ingest Slice 4: stock_balance_snapshot_runs + stock_balance_snapshots.

Run-history report mirror. Explicit idempotent create_table (legacy create_all
DBs skip migration bodies). Chains on Slice 3 (304).

Revision ID: 305_autocount_stock_balance_snapshots
Revises: 304_autocount_item_packages
"""
from alembic import op
import sqlalchemy as sa


revision = "305_autocount_stock_balance_snapshots"
down_revision = "304_autocount_item_packages"
branch_labels = None
depends_on = None

_UUID = sa.dialects.postgresql.UUID


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "stock_balance_snapshot_runs" not in tables:
        op.create_table(
            "stock_balance_snapshot_runs",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("captured_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(30), nullable=False, server_default="autocount"),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        )

    if "stock_balance_snapshots" not in tables:
        op.create_table(
            "stock_balance_snapshots",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("run_id", _UUID(as_uuid=False),
                      sa.ForeignKey("stock_balance_snapshot_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", _UUID(as_uuid=False),
                      sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
            sa.Column("warehouse_id", _UUID(as_uuid=False),
                      sa.ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True),
            sa.Column("item_code", sa.String(100), nullable=False),
            sa.Column("location_code", sa.String(100), nullable=True),
            sa.Column("uom", sa.String(100), nullable=True),
            sa.Column("batch_no", sa.String(100), nullable=True),
            sa.Column("balance", sa.Numeric(15, 4), nullable=True),
            sa.Column("smallest_bal_qty", sa.Numeric(15, 4), nullable=True),
            sa.Column("standard_cost", sa.Numeric(15, 2), nullable=True),
            sa.Column("total_cost", sa.Numeric(15, 2), nullable=True),
            sa.Column("average_cost", sa.Numeric(15, 2), nullable=True),
            sa.Column("rate", sa.Numeric(15, 4), nullable=True),
            sa.Column("description", sa.String(255), nullable=True),
        )
        op.create_index("ix_stock_balance_snapshots_run", "stock_balance_snapshots", ["run_id"])
        op.create_index("ix_stock_balance_snapshots_run_product", "stock_balance_snapshots", ["run_id", "product_id"])


def downgrade() -> None:
    op.drop_table("stock_balance_snapshots")
    op.drop_table("stock_balance_snapshot_runs")
