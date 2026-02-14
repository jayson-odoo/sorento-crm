"""Add sort_order to attachments for drag-to-sort within a folder

Revision ID: 038_attachments_sort_order
Revises: 037_audit_logs_user_id_nullable
Create Date: Add sort_order column to attachments

"""
from alembic import op
import sqlalchemy as sa


revision = '038_attachments_sort_order'
down_revision = '037_audit_logs_user_id_nullable'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('attachments', sa.Column('sort_order', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('attachments', 'sort_order')
