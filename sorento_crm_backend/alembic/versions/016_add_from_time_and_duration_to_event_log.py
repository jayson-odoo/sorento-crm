"""Add from_time and duration to conversation_sla_event_log

Revision ID: 016_add_from_time_duration
Revises: 015_add_responded_by
Create Date: 2026-01-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '016_add_from_time_duration'
down_revision = '015_add_responded_by'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if conversation_sla_event_log table exists
    if 'conversation_sla_event_log' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_event_log')]
    
    # Add from_time column (naive datetime, represents UTC+8)
    if 'from_time' not in columns:
        op.add_column('conversation_sla_event_log', 
                     sa.Column('from_time', sa.DateTime(timezone=False), nullable=True))
    
    # Add duration column (in hours, decimal)
    if 'duration' not in columns:
        op.add_column('conversation_sla_event_log', 
                     sa.Column('duration', sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'conversation_sla_event_log' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_event_log')]
    
    # Drop duration column
    if 'duration' in columns:
        op.drop_column('conversation_sla_event_log', 'duration')
    
    # Drop from_time column
    if 'from_time' in columns:
        op.drop_column('conversation_sla_event_log', 'from_time')
