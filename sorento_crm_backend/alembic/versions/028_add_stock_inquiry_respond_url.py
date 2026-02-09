"""Add contact_id, space_id, respond_inbox_url to stock_inquiries

Revision ID: 028_stock_inquiry_respond
Revises: 027_calendar_and_timestamp
Create Date: Stock inquiry respond.io inbox URL

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '028_stock_inquiry_respond'
down_revision = '027_calendar_and_timestamp'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('stock_inquiries', sa.Column('contact_id', sa.Text(), nullable=True))
    op.add_column('stock_inquiries', sa.Column('space_id', sa.Text(), nullable=True))
    op.add_column('stock_inquiries', sa.Column('respond_inbox_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('stock_inquiries', 'respond_inbox_url')
    op.drop_column('stock_inquiries', 'space_id')
    op.drop_column('stock_inquiries', 'contact_id')
