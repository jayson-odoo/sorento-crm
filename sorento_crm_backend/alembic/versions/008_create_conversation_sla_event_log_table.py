"""Create conversation_sla_event_log table

Revision ID: 008_sla_event_log
Revises: 007_contact_agent_unique
Create Date: 2026-01-24 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008_sla_event_log'
down_revision = '007_contact_agent_unique'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    # Create conversation_sla_event_log table if it doesn't exist
    if 'conversation_sla_event_log' not in tables:
        op.create_table(
            'conversation_sla_event_log',
            sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('sla_tracking_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('conversation_sla_tracking.id', ondelete='CASCADE'), nullable=False),
            sa.Column('event_type', sa.Text(), nullable=False),
            sa.Column('from_tier', sa.Integer(), nullable=True),
            sa.Column('to_tier', sa.Integer(), nullable=True),
            sa.Column('event_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('assigned_to', sa.Text(), nullable=True),
            sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('response_time', sa.Numeric(10, 2), nullable=True),
            sa.Column('resolution_time', sa.Numeric(10, 2), nullable=True),
            sa.Column('reminder_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_reminder_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        
        # Create indexes
        op.create_index('ix_conversation_sla_event_log_sla_tracking_id', 'conversation_sla_event_log', ['sla_tracking_id'])
        op.create_index('ix_conversation_sla_event_log_event_at', 'conversation_sla_event_log', ['event_at'])
        op.create_index('ix_conversation_sla_event_log_event_type', 'conversation_sla_event_log', ['event_type'])


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'conversation_sla_event_log' in inspector.get_table_names():
        # Drop indexes first
        indexes = inspector.get_indexes('conversation_sla_event_log')
        for index in indexes:
            if index['name'].startswith('ix_conversation_sla_event_log'):
                op.drop_index(index['name'], table_name='conversation_sla_event_log')
        
        # Drop table
        op.drop_table('conversation_sla_event_log')
