"""Ensure respond_contact_id has proper foreign key constraint to respond_contacts

Revision ID: 012_ensure_contact_fk
Revises: 011_remove_contact_columns
Create Date: 2026-01-24 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '012_ensure_contact_fk'
down_revision = '011_remove_contact_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if conversation_sla_tracking table exists
    if 'conversation_sla_tracking' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
    
    # Check if respond_contact_id column exists
    if 'respond_contact_id' not in columns:
        # Add the column if it doesn't exist
        op.add_column('conversation_sla_tracking', 
                     sa.Column('respond_contact_id', sa.Text(), nullable=True))
    else:
        # Check if column is nullable - if not, make it nullable first
        column_info = next((col for col in inspector.get_columns('conversation_sla_tracking') if col['name'] == 'respond_contact_id'), None)
        if column_info and not column_info.get('nullable', True):
            # Make the column nullable
            op.alter_column('conversation_sla_tracking', 'respond_contact_id',
                          existing_type=sa.Text(),
                          nullable=True)
    
    # First, clean up any invalid foreign key references
    # Set respond_contact_id to NULL if the contact doesn't exist in respond_contacts
    op.execute(sa.text("""
        UPDATE conversation_sla_tracking cst
        SET respond_contact_id = NULL
        WHERE cst.respond_contact_id IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM respond_contacts rc 
            WHERE rc.id = cst.respond_contact_id
        )
    """))
    
    # Get all foreign keys for the table
    fks = inspector.get_foreign_keys('conversation_sla_tracking')
    fk_exists = any(
        fk['name'] == 'fk_conversation_sla_tracking_respond_contact_id' 
        or (fk['referred_table'] == 'respond_contacts' and 'respond_contact_id' in fk['constrained_columns'])
        for fk in fks
    )
    
    if not fk_exists:
        # Drop any existing foreign key with different name but same columns
        for fk in fks:
            if 'respond_contact_id' in fk.get('constrained_columns', []) and fk['referred_table'] == 'respond_contacts':
                try:
                    op.drop_constraint(fk['name'], 'conversation_sla_tracking', type_='foreignkey')
                except Exception:
                    pass
        
        # Create the foreign key constraint
        op.create_foreign_key(
            'fk_conversation_sla_tracking_respond_contact_id',
            'conversation_sla_tracking', 'respond_contacts',
            ['respond_contact_id'], ['id'],
            ondelete='SET NULL'
        )
    
    # Ensure index exists
    indexes = inspector.get_indexes('conversation_sla_tracking')
    index_exists = any(
        idx['name'] == 'ix_conversation_sla_tracking_respond_contact_id'
        for idx in indexes
    )
    
    if not index_exists:
        op.create_index(
            'ix_conversation_sla_tracking_respond_contact_id',
            'conversation_sla_tracking',
            ['respond_contact_id']
        )
    
    # Ensure unique constraint exists (partial unique index)
    unique_index_exists = any(
        idx['name'] == 'uq_conversation_sla_tracking_respond_contact_id'
        for idx in indexes
    )
    
    if not unique_index_exists:
        op.execute(sa.text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_sla_tracking_respond_contact_id 
            ON conversation_sla_tracking(respond_contact_id) 
            WHERE respond_contact_id IS NOT NULL
        """))


def downgrade() -> None:
    # This migration only ensures constraints exist, no need to downgrade
    pass
