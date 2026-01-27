"""Add missing columns to users table

Revision ID: 002_add_user_columns
Revises: 001_add_is_responded
Create Date: 2026-01-24 01:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_add_user_columns'
down_revision = '001_add_is_responded'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if the columns exist before adding them
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if users table exists
    tables = inspector.get_table_names()
    
    if 'users' in tables:
        # Get existing columns
        columns = [col['name'] for col in inspector.get_columns('users')]
        
        # Add respond_user_id if it doesn't exist
        if 'respond_user_id' not in columns:
            op.add_column('users', 
                         sa.Column('respond_user_id', sa.String(), nullable=True))
        
        # Add respond_synced if it doesn't exist
        if 'respond_synced' not in columns:
            op.add_column('users', 
                         sa.Column('respond_synced', sa.String(), nullable=False, server_default='pending'))
        
        # Add superior_id if it doesn't exist
        if 'superior_id' not in columns:
            op.add_column('users', 
                         sa.Column('superior_id', sa.String(), nullable=True))
            
            # Add foreign key constraint if it doesn't exist
            try:
                op.create_foreign_key(
                    'fk_users_superior_id',
                    'users', 'users',
                    ['superior_id'], ['id']
                )
            except Exception:
                # Foreign key might already exist, ignore
                pass
        
        # Add index for respond_synced if it doesn't exist
        indexes = [idx['name'] for idx in inspector.get_indexes('users')]
        if 'users_respond_synced_idx' not in indexes:
            op.create_index('users_respond_synced_idx', 'users', ['respond_synced'])


def downgrade() -> None:
    # Remove columns if they exist
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'users' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('users')]
        indexes = [idx['name'] for idx in inspector.get_indexes('users')]
        
        # Drop index first
        if 'users_respond_synced_idx' in indexes:
            op.drop_index('users_respond_synced_idx', table_name='users')
        
        # Drop foreign key if it exists
        try:
            op.drop_constraint('fk_users_superior_id', 'users', type_='foreignkey')
        except Exception:
            pass
        
        # Drop columns
        if 'superior_id' in columns:
            op.drop_column('users', 'superior_id')
        if 'respond_synced' in columns:
            op.drop_column('users', 'respond_synced')
        if 'respond_user_id' in columns:
            op.drop_column('users', 'respond_user_id')
