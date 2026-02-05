"""Add responded_by column to conversation_sla_tracking

Revision ID: 015_add_responded_by
Revises: 014_complaint_manual_attachments
Create Date: 2026-01-27 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '015_add_responded_by'
down_revision = '014_complaint_manual_attachments'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if conversation_sla_tracking table exists
    if 'conversation_sla_tracking' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
    
    # Add responded_by column
    if 'responded_by' not in columns:
        op.add_column('conversation_sla_tracking', 
                     sa.Column('responded_by', sa.Text(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'conversation_sla_tracking' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
    
    # Drop responded_by column
    if 'responded_by' in columns:
        op.drop_column('conversation_sla_tracking', 'responded_by')
