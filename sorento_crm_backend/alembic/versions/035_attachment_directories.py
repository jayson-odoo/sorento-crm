"""Add attachment_directories table and attachments.directory_id

Revision ID: 035_attachment_directories
Revises: 034_approval_tokens
Create Date: Directory-based file management for attachments

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '035_attachment_directories'
down_revision = '034_approval_tokens'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'attachment_directories',
        sa.Column('id', UUID(as_uuid=False), primary_key=True),
        sa.Column('parent_id', UUID(as_uuid=False), sa.ForeignKey('attachment_directories.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('sort_order', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_attachment_directories_parent_id', 'attachment_directories', ['parent_id'])

    op.add_column('attachments', sa.Column('directory_id', UUID(as_uuid=False), sa.ForeignKey('attachment_directories.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_attachments_directory_id', 'attachments', ['directory_id'])


def downgrade() -> None:
    op.drop_index('ix_attachments_directory_id', table_name='attachments')
    op.drop_column('attachments', 'directory_id')
    op.drop_index('ix_attachment_directories_parent_id', table_name='attachment_directories')
    op.drop_table('attachment_directories')
