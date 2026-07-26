"""AutoCount ingest Slice 5: orders provenance + ingest-safe annotations.

Reuses the existing `orders` (delivery order) table for AutoCount-ingested DOs.
Adds `sync_source` (provenance: 'autocount' rows are read-only in the UI),
plus the two ingest-safe annotation columns (`internal_note`, `follow_up`)
that ingest never writes, so they survive re-sync — same pair as the new-table
mirrors. Idempotent column adds (legacy create_all DBs may already have them).
Chains on Slice 4 (305).

Revision ID: 306_autocount_orders_provenance
Revises: 305_autocount_stock_balance_snapshots
"""
from alembic import op
import sqlalchemy as sa


revision = "306_autocount_orders_provenance"
down_revision = "305_autocount_stock_balance_snapshots"
branch_labels = None
depends_on = None


def _cols(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if "orders" not in set(sa.inspect(conn).get_table_names()):
        return
    existing = _cols(conn, "orders")

    if "sync_source" not in existing:
        op.add_column(
            "orders",
            sa.Column("sync_source", sa.String(length=32), nullable=False, server_default="manual"),
        )
    if "internal_note" not in existing:
        op.add_column("orders", sa.Column("internal_note", sa.Text(), nullable=True))
    if "follow_up" not in existing:
        op.add_column(
            "orders",
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if "orders" not in set(sa.inspect(conn).get_table_names()):
        return
    existing = _cols(conn, "orders")
    for col in ("follow_up", "internal_note", "sync_source"):
        if col in existing:
            op.drop_column("orders", col)
