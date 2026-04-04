"""Add inquiry_number to stock_inquiries and seed stock_inquiry numbering rule.

Revision ID: 129_stock_inquiry_inquiry_number
Revises: 128_products_list_query_all_master_fields
Create Date: 2026-04-04
"""
from alembic import op
import sqlalchemy as sa


revision = "129_stock_inquiry_inquiry_number"
down_revision = "128_products_list_query_all_master_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_inquiries",
        sa.Column("inquiry_number", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_stock_inquiries_inquiry_number",
        "stock_inquiries",
        ["inquiry_number"],
        unique=False,
    )
    op.execute(
        sa.text("""
            INSERT INTO document_numbering_rules (id, doc_type, enabled, prefix_template, number_digits, next_value, start_value, reset_policy)
            VALUES (gen_random_uuid()::text, 'stock_inquiry', true, 'SI{yy}-', 4, 1, 1, 'yearly')
            ON CONFLICT (doc_type) DO NOTHING
        """)
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM document_numbering_rules WHERE doc_type = 'stock_inquiry'"))
    op.drop_index("ix_stock_inquiries_inquiry_number", table_name="stock_inquiries")
    op.drop_column("stock_inquiries", "inquiry_number")
