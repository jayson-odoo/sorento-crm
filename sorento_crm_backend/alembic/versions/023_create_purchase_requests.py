"""Create purchase_requests and purchase_request_lines tables

Revision ID: 023_create_purchase_requests
Revises: 022_complaint_attachments_link
Create Date: 2026-02-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "023_create_purchase_requests"
down_revision = "022_complaint_attachments_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("request_type", sa.String(length=50), nullable=False),
        sa.Column("request_number", sa.String(length=50), nullable=True),
        sa.Column("request_date", sa.Date(), nullable=True),
        sa.Column("customer_name", sa.Text(), nullable=True),
        sa.Column("project_title", sa.Text(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("expected_po_date", sa.Date(), nullable=True),
        sa.Column("expected_po_date_text", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="external"),
        sa.Column("external_reference", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purchase_requests_request_type", "purchase_requests", ["request_type"])
    op.create_index("ix_purchase_requests_request_date", "purchase_requests", ["request_date"])
    op.create_index("ix_purchase_requests_customer_name", "purchase_requests", ["customer_name"])

    op.create_table(
        "purchase_request_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("purchase_request_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("purchase_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_code", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(15, 2), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purchase_request_lines_purchase_request_id", "purchase_request_lines", ["purchase_request_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_request_lines_purchase_request_id", table_name="purchase_request_lines")
    op.drop_table("purchase_request_lines")
    op.drop_index("ix_purchase_requests_customer_name", table_name="purchase_requests")
    op.drop_index("ix_purchase_requests_request_date", table_name="purchase_requests")
    op.drop_index("ix_purchase_requests_request_type", table_name="purchase_requests")
    op.drop_table("purchase_requests")
