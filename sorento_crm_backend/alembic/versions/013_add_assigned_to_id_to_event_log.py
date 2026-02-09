"""Add assigned_to_id foreign key to conversation_sla_event_log

Revision ID: 013_event_log_assigned_to_id
Revises: 012_ensure_contact_fk
Create Date: 2026-01-24 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '013_event_log_assigned_to_id'
down_revision = '012_ensure_contact_fk'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if conversation_sla_event_log table exists
    if 'conversation_sla_event_log' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_event_log')]
    
    # Add assigned_to_id foreign key (users.id is String, not UUID)
    if 'assigned_to_id' not in columns:
        op.add_column('conversation_sla_event_log', 
                     sa.Column('assigned_to_id', sa.String(), nullable=True))
        
        # Migrate existing data: match assigned_to with users table
        # First try matching by user.id (exact match)
        op.execute(sa.text("""
            UPDATE conversation_sla_event_log el
            SET assigned_to_id = u.id
            FROM users u
            WHERE el.assigned_to = u.id
            AND el.assigned_to IS NOT NULL
            AND el.assigned_to != ''
            AND el.assigned_to_id IS NULL
        """))
        
        # Then try matching by respond_user_id (if assigned_to contains respond_user_id)
        op.execute(sa.text("""
            UPDATE conversation_sla_event_log el
            SET assigned_to_id = u.id
            FROM users u
            WHERE el.assigned_to = u.respond_user_id
            AND el.assigned_to IS NOT NULL
            AND el.assigned_to != ''
            AND u.respond_user_id IS NOT NULL
            AND el.assigned_to_id IS NULL
        """))
        
        # Also try matching by email (in case assigned_to contains email)
        op.execute(sa.text("""
            UPDATE conversation_sla_event_log el
            SET assigned_to_id = u.id
            FROM users u
            WHERE el.assigned_to = u.email
            AND el.assigned_to IS NOT NULL
            AND el.assigned_to != ''
            AND el.assigned_to_id IS NULL
        """))
        
        # Create foreign key constraint
        op.create_foreign_key(
            'fk_conversation_sla_event_log_assigned_to_id',
            'conversation_sla_event_log', 'users',
            ['assigned_to_id'], ['id'],
            ondelete='SET NULL'
        )
        
        # Create index
        op.create_index(
            'ix_conversation_sla_event_log_assigned_to_id',
            'conversation_sla_event_log',
            ['assigned_to_id']
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'conversation_sla_event_log' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_event_log')]
    
    # Drop foreign key and column
    if 'assigned_to_id' in columns:
        # Drop foreign key constraint
        try:
            op.drop_constraint('fk_conversation_sla_event_log_assigned_to_id', 'conversation_sla_event_log', type_='foreignkey')
        except Exception:
            pass
        
        # Drop index
        try:
            op.drop_index('ix_conversation_sla_event_log_assigned_to_id', table_name='conversation_sla_event_log')
        except Exception:
            pass
        
        # Drop column
        op.drop_column('conversation_sla_event_log', 'assigned_to_id')
