"""Create stock_ledger table

Revision ID: 019_create_stock_ledger_table
Revises: 018_create_import_logs
Create Date: 2026-01-28 21:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "019_create_stock_ledger_table"
down_revision = "018_create_import_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "stock_ledger" not in tables:
        op.create_table(
            "stock_ledger",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("warehouse_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("transaction_type", sa.String(length=50), nullable=False),
            sa.Column("quantity_change", sa.Integer(), nullable=False),
            sa.Column("previous_quantity", sa.Integer(), nullable=False),
            sa.Column("new_quantity", sa.Integer(), nullable=False),
            sa.Column("reference_type", sa.String(length=100), nullable=True),
            sa.Column("reference_id", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index("ix_stock_ledger_product_id", "stock_ledger", ["product_id"])
        op.create_index("ix_stock_ledger_warehouse_id", "stock_ledger", ["warehouse_id"])
        op.create_index("ix_stock_ledger_transaction_type", "stock_ledger", ["transaction_type"])
        op.create_index("ix_stock_ledger_created_at", "stock_ledger", ["created_at"])


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "stock_ledger" in tables:
        for index in inspector.get_indexes("stock_ledger"):
            if index["name"].startswith("ix_stock_ledger"):
                op.drop_index(index["name"], table_name="stock_ledger")
        op.drop_table("stock_ledger")
