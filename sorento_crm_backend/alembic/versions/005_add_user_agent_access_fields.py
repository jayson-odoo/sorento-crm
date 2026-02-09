"""Add is_allowed, valid_from, valid_to to user_agent_access

Revision ID: 005_user_agent_access_fields
Revises: 004_respond_contacts
Create Date: 2026-01-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_user_agent_access_fields'
down_revision = '004_respond_contacts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    if 'user_agent_access' in tables:
        columns = [col['name'] for col in inspector.get_columns('user_agent_access')]
        
        # Add is_allowed column if it doesn't exist
        if 'is_allowed' not in columns:
            op.add_column('user_agent_access', 
                         sa.Column('is_allowed', sa.Boolean(), nullable=False, server_default=sa.text('true')))
        
        # Add valid_from column if it doesn't exist
        if 'valid_from' not in columns:
            op.add_column('user_agent_access', 
                         sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True))
        
        # Add valid_to column if it doesn't exist
        if 'valid_to' not in columns:
            op.add_column('user_agent_access', 
                         sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'user_agent_access' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('user_agent_access')]
        
        # Drop columns if they exist
        if 'valid_to' in columns:
            op.drop_column('user_agent_access', 'valid_to')
        if 'valid_from' in columns:
            op.drop_column('user_agent_access', 'valid_from')
        if 'is_allowed' in columns:
            op.drop_column('user_agent_access', 'is_allowed')
