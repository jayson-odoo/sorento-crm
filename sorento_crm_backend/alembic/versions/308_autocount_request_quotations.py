"""AutoCount ingest Slice 7: request_quotations + request_quotation_lines.

New parent+lines document mirror (supplier RFQ). Explicit idempotent
create_table (legacy create_all DBs skip migration bodies). Chains on Slice 6
(307).

Revision ID: 308_autocount_request_quotations
Revises: 307_autocount_quotations
"""
from alembic import op
import sqlalchemy as sa


revision = "308_autocount_request_quotations"
down_revision = "307_autocount_quotations"
branch_labels = None
depends_on = None

_UUID = sa.dialects.postgresql.UUID
_TS = dict(server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())

    if "request_quotations" not in tables:
        op.create_table(
            "request_quotations",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("rq_number", sa.String(100), nullable=False),
            sa.Column("source_doc_no", sa.String(100), nullable=True),
            sa.Column("supplier_id", _UUID(as_uuid=False),
                      sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("creditor_code", sa.String(100), nullable=True),
            sa.Column("creditor_name", sa.String(255), nullable=True),
            sa.Column("doc_date", sa.Date(), nullable=True),
            sa.Column("purchase_agent", sa.String(100), nullable=True),
            sa.Column("internal_note", sa.Text(), nullable=True),
            sa.Column("follow_up", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_unique_constraint("uq_request_quotations_rq_number", "request_quotations", ["rq_number"])
        op.create_index("ix_request_quotations_rq_number", "request_quotations", ["rq_number"])
        op.create_index("ix_request_quotations_creditor_code", "request_quotations", ["creditor_code"])

    if "request_quotation_lines" not in tables:
        op.create_table(
            "request_quotation_lines",
            sa.Column("id", _UUID(as_uuid=False), primary_key=True),
            sa.Column("request_quotation_id", _UUID(as_uuid=False),
                      sa.ForeignKey("request_quotations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", _UUID(as_uuid=False),
                      sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("line_sequence", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("uom", sa.String(100), nullable=True),
            sa.Column("location", sa.String(100), nullable=True),
            sa.Column("qty", sa.Numeric(15, 4), nullable=True),
            sa.Column("unit_price", sa.Numeric(15, 4), nullable=True),
            sa.Column("sub_total", sa.Numeric(15, 2), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=False), **_TS),
            sa.Column("updated_at", sa.DateTime(timezone=False), **_TS),
        )
        op.create_index("ix_request_quotation_lines_rq_id", "request_quotation_lines", ["request_quotation_id"])
        op.create_index("ix_request_quotation_lines_product_id", "request_quotation_lines", ["product_id"])


def downgrade() -> None:
    op.drop_table("request_quotation_lines")
    op.drop_table("request_quotations")
