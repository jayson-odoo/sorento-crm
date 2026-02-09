"""Stock inquiry: quantity/delivery_date as string, brand -> remark

Revision ID: 029_stock_inquiry_string_remark
Revises: 028_stock_inquiry_respond
Create Date: Stock inquiry quantity delivery remark

"""
from alembic import op
import sqlalchemy as sa


revision = '029_stock_inquiry_string_remark'
down_revision = '028_stock_inquiry_respond'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert quantity from numeric to text (preserve existing values as string)
    op.alter_column(
        'stock_inquiries',
        'quantity',
        existing_type=sa.Numeric(15, 2),
        type_=sa.Text(),
        postgresql_using='quantity::text',
    )
    # Convert delivery_date from date to text
    op.alter_column(
        'stock_inquiries',
        'delivery_date',
        existing_type=sa.Date(),
        type_=sa.Text(),
        postgresql_using='delivery_date::text',
    )
    # Rename brand to remark
    op.alter_column(
        'stock_inquiries',
        'brand',
        new_column_name='remark',
    )


def downgrade() -> None:
    op.alter_column(
        'stock_inquiries',
        'remark',
        new_column_name='brand',
    )
    op.alter_column(
        'stock_inquiries',
        'delivery_date',
        existing_type=sa.Text(),
        type_=sa.Date(),
        postgresql_using='delivery_date::date',
    )
    op.alter_column(
        'stock_inquiries',
        'quantity',
        existing_type=sa.Text(),
        type_=sa.Numeric(15, 2),
        postgresql_using='quantity::numeric(15,2)',
    )
