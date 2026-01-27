"""Add missing columns including is_responded to SLA tracking

Revision ID: 001_add_is_responded
Revises: 
Create Date: 2026-01-24 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_add_is_responded'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if the column exists before adding it
    connection = op.get_bind()
    
    # Check if conversation_sla_tracking table exists
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    if 'conversation_sla_tracking' in tables:
        # Check if is_responded column already exists
        columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
        
        if 'is_responded' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('is_responded', sa.Boolean(), nullable=False, server_default='false'))
        
        # Add other missing columns if they don't exist
        if 'responded_at' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True))
        
        if 'response_time' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('response_time', sa.Numeric(10, 2), nullable=True))
        
        if 'is_resolved' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'))
        
        if 'resolved_at' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
        
        if 'resolved_by' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('resolved_by', sa.Text(), nullable=True))
        
        if 'respond_contact_phone' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('respond_contact_phone', sa.Text(), nullable=False, server_default=''))
        
        if 'respond_contact_name' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('respond_contact_name', sa.Text(), nullable=True))
        
        if 'synced_to_excel' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('synced_to_excel', sa.Boolean(), nullable=False, server_default='false'))
        
        if 'last_synced_to_excel' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('last_synced_to_excel', sa.DateTime(timezone=True), nullable=True))
        
        if 'resolution_duration' not in columns:
            op.add_column('conversation_sla_tracking', 
                         sa.Column('resolution_duration', sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    # Remove columns if they exist
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'conversation_sla_tracking' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
        
        if 'resolution_duration' in columns:
            op.drop_column('conversation_sla_tracking', 'resolution_duration')
        if 'last_synced_to_excel' in columns:
            op.drop_column('conversation_sla_tracking', 'last_synced_to_excel')
        if 'synced_to_excel' in columns:
            op.drop_column('conversation_sla_tracking', 'synced_to_excel')
        if 'respond_contact_name' in columns:
            op.drop_column('conversation_sla_tracking', 'respond_contact_name')
        if 'respond_contact_phone' in columns:
            op.drop_column('conversation_sla_tracking', 'respond_contact_phone')
        if 'resolved_by' in columns:
            op.drop_column('conversation_sla_tracking', 'resolved_by')
        if 'resolved_at' in columns:
            op.drop_column('conversation_sla_tracking', 'resolved_at')
        if 'is_resolved' in columns:
            op.drop_column('conversation_sla_tracking', 'is_resolved')
        if 'response_time' in columns:
            op.drop_column('conversation_sla_tracking', 'response_time')
        if 'responded_at' in columns:
            op.drop_column('conversation_sla_tracking', 'responded_at')
        if 'is_responded' in columns:
            op.drop_column('conversation_sla_tracking', 'is_responded')
