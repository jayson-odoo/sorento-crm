"""Rename respond_contact_id to respond_contact_phone and add respond_contact_name

Revision ID: 003_rename_contact_id_to_phone
Revises: 002_add_user_columns
Create Date: 2026-01-24 02:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_rename_contact_id_to_phone'
down_revision = '002_add_user_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    if 'contact_agent_access' in tables:
        columns = [col['name'] for col in inspector.get_columns('contact_agent_access')]
        indexes = [idx['name'] for idx in inspector.get_indexes('contact_agent_access')]
        
        # Rename respond_contact_id to respond_contact_phone if it exists
        if 'respond_contact_id' in columns and 'respond_contact_phone' not in columns:
            op.alter_column('contact_agent_access', 'respond_contact_id', 
                         new_column_name='respond_contact_phone')
        
        # Add respond_contact_name if it doesn't exist
        if 'respond_contact_name' not in columns:
            op.add_column('contact_agent_access', 
                         sa.Column('respond_contact_name', sa.Text(), nullable=True))
        
        # Update indexes
        if 'ix_contact_agent_access_respond_contact_id' in indexes:
            op.drop_index('ix_contact_agent_access_respond_contact_id', table_name='contact_agent_access')
        
        # Create new index for respond_contact_phone if it doesn't exist
        new_indexes = [idx['name'] for idx in inspector.get_indexes('contact_agent_access')]
        if 'ix_contact_agent_access_respond_contact_phone' not in new_indexes:
            op.create_index('ix_contact_agent_access_respond_contact_phone', 
                          'contact_agent_access', ['respond_contact_phone'])
        
        # Update unique constraint if it exists
        constraints = [c['name'] for c in inspector.get_unique_constraints('contact_agent_access')]
        if 'uq_contact_agent_access_respond_contact_phone_agent_id' not in constraints:
            # Drop old constraint if it exists with old name
            old_constraints = [c for c in inspector.get_unique_constraints('contact_agent_access')]
            for constraint in old_constraints:
                if 'respond_contact' in str(constraint.get('column_names', [])):
                    try:
                        op.drop_constraint(constraint['name'], 'contact_agent_access', type_='unique')
                    except Exception:
                        pass
            
            # Create new unique constraint
            op.create_unique_constraint('uq_contact_agent_access_respond_contact_phone_agent_id',
                                      'contact_agent_access',
                                      ['respond_contact_phone', 'agent_id'])


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'contact_agent_access' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('contact_agent_access')]
        indexes = [idx['name'] for idx in inspector.get_indexes('contact_agent_access')]
        constraints = [c['name'] for c in inspector.get_unique_constraints('contact_agent_access')]
        
        # Drop respond_contact_name if it exists
        if 'respond_contact_name' in columns:
            op.drop_column('contact_agent_access', 'respond_contact_name')
        
        # Rename respond_contact_phone back to respond_contact_id if it exists
        if 'respond_contact_phone' in columns and 'respond_contact_id' not in columns:
            op.alter_column('contact_agent_access', 'respond_contact_phone',
                          new_column_name='respond_contact_id')
        
        # Update indexes
        if 'ix_contact_agent_access_respond_contact_phone' in indexes:
            op.drop_index('ix_contact_agent_access_respond_contact_phone', table_name='contact_agent_access')
        
        new_indexes = [idx['name'] for idx in inspector.get_indexes('contact_agent_access')]
        if 'ix_contact_agent_access_respond_contact_id' not in new_indexes:
            op.create_index('ix_contact_agent_access_respond_contact_id',
                          'contact_agent_access', ['respond_contact_id'])
