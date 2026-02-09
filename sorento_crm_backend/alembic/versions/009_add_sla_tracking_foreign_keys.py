"""Add foreign keys to conversation_sla_tracking for contacts and users

Revision ID: 009_sla_tracking_fks
Revises: 008_sla_event_log
Create Date: 2026-01-24 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '009_sla_tracking_fks'
down_revision = '008_sla_event_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if conversation_sla_tracking table exists
    if 'conversation_sla_tracking' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
    
    # Add respond_contact_id foreign key
    if 'respond_contact_id' not in columns:
        op.add_column('conversation_sla_tracking', 
                     sa.Column('respond_contact_id', sa.Text(), nullable=True))
        
        # Migrate existing data: match by phone_number
        # Try exact match first, then try with/without leading +, and handle whitespace
        op.execute(sa.text("""
            UPDATE conversation_sla_tracking cst
            SET respond_contact_id = rc.id
            FROM respond_contacts rc
            WHERE (
                -- Exact match
                cst.respond_contact_phone = rc.phone_number
                -- Match with normalized phone numbers (remove +, spaces, dashes)
                OR REPLACE(REPLACE(REPLACE(cst.respond_contact_phone, '+', ''), ' ', ''), '-', '') = 
                   REPLACE(REPLACE(REPLACE(rc.phone_number, '+', ''), ' ', ''), '-', '')
                -- Match if one has + and other doesn't
                OR cst.respond_contact_phone = '+' || rc.phone_number
                OR '+' || cst.respond_contact_phone = rc.phone_number
            )
            AND cst.respond_contact_phone IS NOT NULL
            AND cst.respond_contact_phone != ''
            AND cst.respond_contact_id IS NULL
        """))
        
        # Create foreign key constraint
        op.create_foreign_key(
            'fk_conversation_sla_tracking_respond_contact_id',
            'conversation_sla_tracking', 'respond_contacts',
            ['respond_contact_id'], ['id'],
            ondelete='SET NULL'
        )
        
        # Create index
        op.create_index(
            'ix_conversation_sla_tracking_respond_contact_id',
            'conversation_sla_tracking',
            ['respond_contact_id']
        )
    
    # Add assigned_to_id foreign key (users.id is String, not UUID)
    if 'assigned_to_id' not in columns:
        op.add_column('conversation_sla_tracking', 
                     sa.Column('assigned_to_id', sa.String(), nullable=True))
        
        # Migrate existing data: match assigned_to with users table
        # First try matching by user.id (exact match)
        op.execute(sa.text("""
            UPDATE conversation_sla_tracking cst
            SET assigned_to_id = u.id
            FROM users u
            WHERE cst.assigned_to = u.id
            AND cst.assigned_to IS NOT NULL
            AND cst.assigned_to != ''
            AND cst.assigned_to_id IS NULL
        """))
        
        # Then try matching by respond_user_id (if assigned_to contains respond_user_id)
        op.execute(sa.text("""
            UPDATE conversation_sla_tracking cst
            SET assigned_to_id = u.id
            FROM users u
            WHERE cst.assigned_to = u.respond_user_id
            AND cst.assigned_to IS NOT NULL
            AND cst.assigned_to != ''
            AND u.respond_user_id IS NOT NULL
            AND cst.assigned_to_id IS NULL
        """))
        
        # Also try matching by email (in case assigned_to contains email)
        op.execute(sa.text("""
            UPDATE conversation_sla_tracking cst
            SET assigned_to_id = u.id
            FROM users u
            WHERE cst.assigned_to = u.email
            AND cst.assigned_to IS NOT NULL
            AND cst.assigned_to != ''
            AND cst.assigned_to_id IS NULL
        """))
        
        # Create foreign key constraint
        op.create_foreign_key(
            'fk_conversation_sla_tracking_assigned_to_id',
            'conversation_sla_tracking', 'users',
            ['assigned_to_id'], ['id'],
            ondelete='SET NULL'
        )
        
        # Create index
        op.create_index(
            'ix_conversation_sla_tracking_assigned_to_id',
            'conversation_sla_tracking',
            ['assigned_to_id']
        )
    
    # Update unique constraint: remove old one on respond_contact_phone, add new one on respond_contact_id
    # First check if the old unique constraint exists
    constraints = inspector.get_unique_constraints('conversation_sla_tracking')
    old_constraint_name = None
    for constraint in constraints:
        if 'respond_contact_phone' in constraint.get('column_names', []):
            old_constraint_name = constraint['name']
            break
    
    if old_constraint_name:
        try:
            op.drop_constraint(old_constraint_name, 'conversation_sla_tracking', type_='unique')
        except Exception:
            # Try dropping as index if constraint drop fails
            try:
                op.drop_index(old_constraint_name, table_name='conversation_sla_tracking')
            except Exception:
                pass
    
    # Add new unique constraint on respond_contact_id (only where not null)
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_sla_tracking_respond_contact_id 
        ON conversation_sla_tracking(respond_contact_id) 
        WHERE respond_contact_id IS NOT NULL
    """))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'conversation_sla_tracking' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
    
    # Drop foreign keys and columns
    if 'assigned_to_id' in columns:
        # Drop foreign key constraint
        try:
            op.drop_constraint('fk_conversation_sla_tracking_assigned_to_id', 'conversation_sla_tracking', type_='foreignkey')
        except Exception:
            pass
        
        # Drop index
        try:
            op.drop_index('ix_conversation_sla_tracking_assigned_to_id', table_name='conversation_sla_tracking')
        except Exception:
            pass
        
        # Drop column
        op.drop_column('conversation_sla_tracking', 'assigned_to_id')
    
    if 'respond_contact_id' in columns:
        # Drop unique index
        try:
            op.execute(sa.text("DROP INDEX IF EXISTS uq_conversation_sla_tracking_respond_contact_id"))
        except Exception:
            pass
        
        # Drop foreign key constraint
        try:
            op.drop_constraint('fk_conversation_sla_tracking_respond_contact_id', 'conversation_sla_tracking', type_='foreignkey')
        except Exception:
            pass
        
        # Drop index
        try:
            op.drop_index('ix_conversation_sla_tracking_respond_contact_id', table_name='conversation_sla_tracking')
        except Exception:
            pass
        
        # Drop column
        op.drop_column('conversation_sla_tracking', 'respond_contact_id')
    
    # Recreate old unique constraint on respond_contact_phone
    op.create_unique_constraint(
        'uq_conversation_sla_tracking_respond_contact_phone',
        'conversation_sla_tracking',
        ['respond_contact_phone']
    )
