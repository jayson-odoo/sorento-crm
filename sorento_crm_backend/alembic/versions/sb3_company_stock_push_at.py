"""`companies` gains `stock_push_confirmed_at` (fix: stock "Data last updated").

The chatbot's "_Data last updated_" footer read the latest BULK_IMPORT ledger
row, but the AutoCount `stock_balances` push (contract 2.5) writes no ledger
row and leaves `stock.updated_at` alone when a value is unchanged, so a push
every 5 minutes never moved the footer. Every accepted push batch now stamps
this column for its company, and the footer reads the latest of it and the
last BULK_IMPORT for the companies in the answer.

One nullable column on the existing per-company row: a company that has
never been pushed stays NULL and keeps reading its last import.

Revision ID: sb3_company_stock_push_at
Revises: sb2_stock_pair_unique
"""
import sqlalchemy as sa
from alembic import op

revision = "sb3_company_stock_push_at"
down_revision = "sb2_stock_pair_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("stock_push_confirmed_at", sa.DateTime(timezone=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "stock_push_confirmed_at")
