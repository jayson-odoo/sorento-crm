"""AutoCount DO and GRN ingest (#1354 S2): branch table, identity, typed and link columns.

Plan: documentation/plans/autocount/PLAN-autocount-grn-do-ingest-29sep.md, section 2.

1. `branches`: the CRM's copy of AutoCount's branch table (ruling Q2), company scoped, unique
   `(company_id, source_book, acc_no, branch_code)`, the row as sent in `source_record`.
2. `orders` / `order_lines` (ruling Q3) and `picking_headers` / `picking_lines` (ruling Q4):
   the AutoCount identity (`source_book`, `doc_key`, `dtl_key`), provenance
   (`source_modified_at`, `source_vanished_at`, `last_synced_at`), the full record as sent
   (`source_record`, ruling Q1), the typed columns the CRM reads, and the link columns
   (`orders.sales_order_id`, `picking_lines.purchase_order_id`; the line links
   `order_lines.sales_order_line_id`, `picking_lines.po_line_id` and
   `picking_lines.spo_allocation_id` already exist).
3. Partial unique indexes: one document per `(company, book, DocKey)`, one line per
   `(header, DtlKey)`.

Every column is nullable (or has a default), so no existing row is touched and the tracking
upload keeps writing exactly what it wrote. Downgrade drops everything this adds.

Revision ID: ac_grn_do_0001_ingest
Revises: sales_agent_aliases_r7
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ac_grn_do_0001_ingest"
down_revision = "sales_agent_aliases_r7"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=False)
_JSON = postgresql.JSONB(astext_type=sa.Text())


def _identity_columns() -> list[sa.Column]:
    return [
        sa.Column("source_book", sa.String(20), nullable=True),
        sa.Column("doc_key", sa.BigInteger(), nullable=True),
        sa.Column("source_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_vanished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("source_record", _JSON, nullable=True),
    ]


def _header_text_columns() -> list[sa.Column]:
    return [
        sa.Column("ship_via", sa.String(100), nullable=True),
        sa.Column("ship_info", sa.String(255), nullable=True),
        sa.Column("ref", sa.String(255), nullable=True),
        sa.Column("ref_doc_no", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("doc_status", sa.String(20), nullable=True),
        sa.Column("currency_code", sa.String(10), nullable=True),
        sa.Column("currency_rate", sa.Numeric(18, 8), nullable=True),
        sa.Column("local_net_total", sa.Numeric(15, 2), nullable=True),
    ]


def _line_columns() -> list[sa.Column]:
    return [
        sa.Column("dtl_key", sa.BigInteger(), nullable=True),
        sa.Column("item_code", sa.String(100), nullable=True),
        sa.Column("location_code", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("foc_qty", sa.Numeric(15, 4), nullable=True),
        sa.Column("discount_text", sa.String(50), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("proj_no", sa.String(50), nullable=True),
        sa.Column("from_doc_type", sa.String(10), nullable=True),
        sa.Column("from_doc_no", sa.String(100), nullable=True),
        sa.Column("from_dtl_key", sa.BigInteger(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("company_id", _UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("source_book", sa.String(20), nullable=False),
        sa.Column("acc_no", sa.String(100), nullable=False, server_default=""),
        sa.Column("branch_code", sa.String(100), nullable=False),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("source_record", _JSON, nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_branches_company_id", "branches", ["company_id"])
    op.create_index(
        "uq_branches_company_book_acc_code",
        "branches",
        ["company_id", "source_book", "acc_no", "branch_code"],
        unique=True,
    )

    # ------------------------------------------------------------------ orders
    for column in _identity_columns() + _header_text_columns() + [
        sa.Column("branch_code", sa.String(100), nullable=True),
        sa.Column("branch_name", sa.String(255), nullable=True),
        sa.Column("deliver_address", sa.Text(), nullable=True),
        sa.Column("deliver_contact", sa.String(255), nullable=True),
        sa.Column("deliver_phone", sa.String(100), nullable=True),
        sa.Column(
            "sales_order_id",
            _UUID,
            sa.ForeignKey("sales_orders.id", ondelete="SET NULL",
                          name="fk_orders_sales_order_id"),
            nullable=True,
        ),
    ]:
        op.add_column("orders", column)
    op.create_index(
        "uq_orders_company_book_doc_key",
        "orders",
        ["company_id", "source_book", "doc_key"],
        unique=True,
        postgresql_where=sa.text("doc_key IS NOT NULL"),
    )
    op.create_index("ix_orders_sales_order_id", "orders", ["sales_order_id"])

    # ------------------------------------------------------------- order_lines
    for column in _line_columns() + [
        sa.Column("uom", sa.String(30), nullable=True),
        sa.Column("batch_no", sa.String(100), nullable=True),
        sa.Column("your_po_no", sa.String(100), nullable=True),
        sa.Column("your_po_date", sa.Date(), nullable=True),
    ]:
        op.add_column("order_lines", column)
    op.create_index(
        "uq_order_lines_order_dtl_key",
        "order_lines",
        ["order_id", "dtl_key"],
        unique=True,
        postgresql_where=sa.text("dtl_key IS NOT NULL"),
    )

    # --------------------------------------------------------- picking_headers
    for column in _identity_columns() + _header_text_columns() + [
        sa.Column("creditor_code", sa.String(100), nullable=True),
        sa.Column("creditor_name", sa.String(255), nullable=True),
        sa.Column("supplier_do_no", sa.String(100), nullable=True),
        sa.Column("purchase_agent", sa.String(100), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("subtotal_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=True),
    ]:
        op.add_column("picking_headers", column)
    op.create_index(
        "uq_picking_headers_company_book_doc_key",
        "picking_headers",
        ["company_id", "source_book", "doc_key"],
        unique=True,
        postgresql_where=sa.text("doc_key IS NOT NULL"),
    )

    # ----------------------------------------------------------- picking_lines
    for column in _line_columns() + [
        # `uom_code`: the model's `uom` is its UnitOfMeasure relationship.
        sa.Column("uom_code", sa.String(30), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=True),
        sa.Column("qty", sa.Numeric(15, 4), nullable=True),
        sa.Column("discount_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("our_po_no", sa.String(100), nullable=True),
        sa.Column("our_po_date", sa.Date(), nullable=True),
        sa.Column(
            "purchase_order_id",
            _UUID,
            sa.ForeignKey("purchase_orders.id", ondelete="SET NULL",
                          name="fk_picking_lines_purchase_order_id"),
            nullable=True,
        ),
    ]:
        op.add_column("picking_lines", column)
    op.create_index(
        "uq_picking_lines_header_dtl_key",
        "picking_lines",
        ["picking_header_id", "dtl_key"],
        unique=True,
        postgresql_where=sa.text("dtl_key IS NOT NULL"),
    )
    op.create_index("ix_picking_lines_purchase_order_id", "picking_lines", ["purchase_order_id"])


def _drop(table: str, columns: list[str]) -> None:
    for name in columns:
        op.drop_column(table, name)


def downgrade() -> None:
    op.drop_index("ix_picking_lines_purchase_order_id", table_name="picking_lines")
    op.drop_index("uq_picking_lines_header_dtl_key", table_name="picking_lines")
    _drop("picking_lines", [c.name for c in _line_columns()] + [
        "uom_code", "seq", "qty", "discount_amount", "tax_amount", "our_po_no", "our_po_date",
        "purchase_order_id",
    ])

    op.drop_index("uq_picking_headers_company_book_doc_key", table_name="picking_headers")
    _drop("picking_headers", [c.name for c in _identity_columns() + _header_text_columns()] + [
        "creditor_code", "creditor_name", "supplier_do_no", "purchase_agent", "remarks",
        "is_cancelled", "subtotal_amount", "tax_amount", "total_amount",
    ])

    op.drop_index("uq_order_lines_order_dtl_key", table_name="order_lines")
    _drop("order_lines", [c.name for c in _line_columns()] + [
        "uom", "batch_no", "your_po_no", "your_po_date",
    ])

    op.drop_index("ix_orders_sales_order_id", table_name="orders")
    op.drop_index("uq_orders_company_book_doc_key", table_name="orders")
    _drop("orders", [c.name for c in _identity_columns() + _header_text_columns()] + [
        "branch_code", "branch_name", "deliver_address", "deliver_contact", "deliver_phone",
        "sales_order_id",
    ])

    op.drop_index("uq_branches_company_book_acc_code", table_name="branches")
    op.drop_index("ix_branches_company_id", table_name="branches")
    op.drop_table("branches")
