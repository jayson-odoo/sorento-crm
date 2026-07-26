"""AutoCount ingest Slice 8: SO/PO reuse — ALTER line tables + annotation cols.

Reuses the existing SCM ``sales_orders`` / ``purchase_orders`` (+ their line
tables) for AutoCount-ingested SO/PO. Adds:
  - pricing columns the AutoCount SODTL/PODTL carry but the SCM lines lack;
  - the two ingest-safe annotation columns on each header (internal_note,
    follow_up), matching every other mirror.
Provenance reuses the existing ``source_system``/``source_ref`` columns already
on these tables (source_system='autocount'); no new provenance column.

Idempotent column adds (legacy create_all DBs may already have them). Chains on
Slice 7 (308).

Revision ID: 309_autocount_so_po_pricing
Revises: 308_autocount_request_quotations
"""
from alembic import op
import sqlalchemy as sa


revision = "309_autocount_so_po_pricing"
down_revision = "308_autocount_request_quotations"
branch_labels = None
depends_on = None


def _cols(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _add(table: str, column: sa.Column, existing: set[str]) -> None:
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "sales_orders" in tables:
        e = _cols(conn, "sales_orders")
        _add("sales_orders", sa.Column("source_doc_no", sa.String(100), nullable=True), e)
        _add("sales_orders", sa.Column("internal_note", sa.Text(), nullable=True), e)
        _add("sales_orders", sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")), e)

    if "sales_order_lines" in tables:
        e = _cols(conn, "sales_order_lines")
        _add("sales_order_lines", sa.Column("unit_price", sa.Numeric(15, 2), nullable=True), e)
        _add("sales_order_lines", sa.Column("discount_amt", sa.Numeric(15, 2), nullable=True), e)
        _add("sales_order_lines", sa.Column("tax_rate", sa.Numeric(9, 4), nullable=True), e)
        _add("sales_order_lines", sa.Column("tax_amt", sa.Numeric(15, 2), nullable=True), e)
        _add("sales_order_lines", sa.Column("sub_total", sa.Numeric(15, 2), nullable=True), e)
        _add("sales_order_lines", sa.Column("delivery_date", sa.Date(), nullable=True), e)
        _add("sales_order_lines", sa.Column("uom", sa.String(100), nullable=True), e)
        _add("sales_order_lines", sa.Column("tax_code", sa.String(100), nullable=True), e)

    if "purchase_orders" in tables:
        e = _cols(conn, "purchase_orders")
        _add("purchase_orders", sa.Column("source_doc_no", sa.String(100), nullable=True), e)
        _add("purchase_orders", sa.Column("internal_note", sa.Text(), nullable=True), e)
        _add("purchase_orders", sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")), e)

    if "purchase_order_lines" in tables:
        e = _cols(conn, "purchase_order_lines")
        _add("purchase_order_lines", sa.Column("description", sa.String(500), nullable=True), e)
        _add("purchase_order_lines", sa.Column("sub_total", sa.Numeric(15, 2), nullable=True), e)


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "purchase_order_lines" in tables:
        e = _cols(conn, "purchase_order_lines")
        for c in ("sub_total", "description"):
            if c in e:
                op.drop_column("purchase_order_lines", c)
    if "purchase_orders" in tables:
        e = _cols(conn, "purchase_orders")
        for c in ("follow_up", "internal_note", "source_doc_no"):
            if c in e:
                op.drop_column("purchase_orders", c)
    if "sales_order_lines" in tables:
        e = _cols(conn, "sales_order_lines")
        for c in ("tax_code", "uom", "delivery_date", "sub_total", "tax_amt", "tax_rate", "discount_amt", "unit_price"):
            if c in e:
                op.drop_column("sales_order_lines", c)
    if "sales_orders" in tables:
        e = _cols(conn, "sales_orders")
        for c in ("follow_up", "internal_note", "source_doc_no"):
            if c in e:
                op.drop_column("sales_orders", c)
