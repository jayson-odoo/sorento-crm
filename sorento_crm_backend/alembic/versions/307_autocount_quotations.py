"""AutoCount ingest Slice 6: quotations + quotation_lines.

New parent+lines document mirror. Explicit idempotent create_table (legacy
create_all DBs skip migration bodies). Chains on Slice 5 (306).

Revision ID: 307_autocount_quotations
Revises: 306_autocount_orders_provenance
"""
from alembic import op
import sqlalchemy as sa


revision = "307_autocount_quotations"
down_revision = "306_autocount_orders_provenance"
branch_labels = None
depends_on = None

_UUID = sa.dialects.postgresql.UUID
_TS = dict(server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "quotations" not in tables:
        op.create_table(
            "quotations",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("quote_number", sa.String(100), nullable=False),
            sa.Column("source_doc_no", sa.String(100), nullable=True),
            sa.Column("debtor_code", sa.String(100), nullable=True),
            sa.Column("debtor_name", sa.String(255), nullable=True),
            sa.Column("doc_date", sa.Date(), nullable=True),
            sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("attention", sa.String(255), nullable=True),
            sa.Column("branch_code", sa.String(100), nullable=True),
            sa.Column("deliver_addr1", sa.String(255), nullable=True),
            sa.Column("deliver_addr2", sa.String(255), nullable=True),
            sa.Column("deliver_addr3", sa.String(255), nullable=True),
            sa.Column("deliver_addr4", sa.String(255), nullable=True),
            sa.Column("terms", sa.String(255), nullable=True),
            sa.Column("sales_agent", sa.String(100), nullable=True),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_unique_constraint("uq_quotations_quote_number", "quotations", ["quote_number"])
        op.create_index("ix_quotations_quote_number", "quotations", ["quote_number"])
        op.create_index("ix_quotations_debtor_code", "quotations", ["debtor_code"])

    if "quotation_lines" not in tables:
        op.create_table(
            "quotation_lines",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("quotation_id", _UUID(as_uuid=False),
                      sa.ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", _UUID(as_uuid=False),
                      sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("line_sequence", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("uom", sa.String(100), nullable=True),
            sa.Column("location", sa.String(100), nullable=True),
            sa.Column("qty", sa.Numeric(15, 4), nullable=True),
            sa.Column("unit_price", sa.Numeric(15, 4), nullable=True),
            sa.Column("sub_total", sa.Numeric(15, 2), nullable=True),
            sa.Column("discount_amt", sa.Numeric(15, 2), nullable=True),
            sa.Column("tax_code", sa.String(100), nullable=True),
            sa.Column("tax_rate", sa.Numeric(9, 4), nullable=True),
            sa.Column("tax", sa.Numeric(15, 2), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("further_description", sa.Text(), nullable=True),
            sa.Column("package_code", sa.String(100), nullable=True),
            sa.Column("proj_no", sa.String(100), nullable=True),
            sa.Column("dept_no", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_index("ix_quotation_lines_quotation_id", "quotation_lines", ["quotation_id"])
        op.create_index("ix_quotation_lines_product_id", "quotation_lines", ["product_id"])


def downgrade() -> None:
    op.drop_table("quotation_lines")
    op.drop_table("quotations")
