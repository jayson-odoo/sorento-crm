"""Add status and response fields to stock_inquiries and complaints

Revision ID: 031_inquiry_complaint
Revises: 030_respond_complaints_pr
Create Date: Status (new/updated/responded) and last_responded for Update & Reply

"""
from alembic import op
import sqlalchemy as sa


revision = '031_inquiry_complaint'
down_revision = '030_respond_complaints_pr'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stock inquiries: status, last_responded_by, last_responded_at
    op.add_column('stock_inquiries', sa.Column('status', sa.String(50), nullable=True))
    op.add_column('stock_inquiries', sa.Column('last_responded_by', sa.Text(), nullable=True))
    op.add_column('stock_inquiries', sa.Column('last_responded_at', sa.DateTime(timezone=False), nullable=True))
    op.execute("UPDATE stock_inquiries SET status = 'new' WHERE status IS NULL")
    op.alter_column('stock_inquiries', 'status', nullable=False, server_default='new')

    # Complaints: technical_team_response, status, last_responded_by, last_responded_at
    op.add_column('complaints', sa.Column('technical_team_response', sa.Text(), nullable=True))
    op.add_column('complaints', sa.Column('status', sa.String(50), nullable=True))
    op.add_column('complaints', sa.Column('last_responded_by', sa.Text(), nullable=True))
    op.add_column('complaints', sa.Column('last_responded_at', sa.DateTime(timezone=False), nullable=True))
    op.execute("UPDATE complaints SET status = 'new' WHERE status IS NULL")
    op.alter_column('complaints', 'status', nullable=False, server_default='new')


def downgrade() -> None:
    op.drop_column('complaints', 'last_responded_at')
    op.drop_column('complaints', 'last_responded_by')
    op.drop_column('complaints', 'status')
    op.drop_column('complaints', 'technical_team_response')

    op.drop_column('stock_inquiries', 'last_responded_at')
    op.drop_column('stock_inquiries', 'last_responded_by')
    op.drop_column('stock_inquiries', 'status')
