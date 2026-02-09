"""Add contact_id, space_id, respond_inbox_url to complaints and purchase_requests

Revision ID: 030_respond_complaints_pr
Revises: 029_stock_inquiry_string_remark
Create Date: Respond conversation URL for complaint, purchase request, sponsorship form

"""
from alembic import op
import sqlalchemy as sa


revision = '030_respond_complaints_pr'
down_revision = '029_stock_inquiry_string_remark'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('complaints', sa.Column('contact_id', sa.Text(), nullable=True))
    op.add_column('complaints', sa.Column('space_id', sa.Text(), nullable=True))
    op.add_column('complaints', sa.Column('respond_inbox_url', sa.Text(), nullable=True))

    op.add_column('purchase_requests', sa.Column('contact_id', sa.Text(), nullable=True))
    op.add_column('purchase_requests', sa.Column('space_id', sa.Text(), nullable=True))
    op.add_column('purchase_requests', sa.Column('respond_inbox_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('purchase_requests', 'respond_inbox_url')
    op.drop_column('purchase_requests', 'space_id')
    op.drop_column('purchase_requests', 'contact_id')

    op.drop_column('complaints', 'respond_inbox_url')
    op.drop_column('complaints', 'space_id')
    op.drop_column('complaints', 'contact_id')
