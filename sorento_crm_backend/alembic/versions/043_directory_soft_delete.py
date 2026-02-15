"""Add soft-delete to attachment_directories for folder restore

Revision ID: 043_directory_soft_delete
Revises: 042_forms_attach_setnull
Create Date: is_deleted, deleted_at, deleted_by on attachment_directories

"""
from alembic import op
import sqlalchemy as sa


revision = '043_dir_soft_delete'
down_revision = '042_forms_attach_setnull'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('attachment_directories', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('attachment_directories', sa.Column('deleted_at', sa.DateTime(timezone=False), nullable=True))
    op.add_column('attachment_directories', sa.Column('deleted_by', sa.String(), nullable=True))
    op.create_index('ix_attachment_directories_is_deleted', 'attachment_directories', ['is_deleted'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_attachment_directories_is_deleted', 'attachment_directories')
    op.drop_column('attachment_directories', 'deleted_by')
    op.drop_column('attachment_directories', 'deleted_at')
    op.drop_column('attachment_directories', 'is_deleted')
