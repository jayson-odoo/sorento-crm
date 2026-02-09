"""Remove unique constraint on respond_contact_phone and agent_id

Revision ID: 006_remove_contact_agent_unique
Revises: 005_user_agent_access_fields
Create Date: 2026-01-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_remove_contact_agent_unique'
down_revision = '005_user_agent_access_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'contact_agent_access' in inspector.get_table_names():
        # Get all constraints on the table
        constraints = inspector.get_unique_constraints('contact_agent_access')
        
        # Find and drop the unique constraint
        for constraint in constraints:
            if constraint['name'] == 'uq_contact_agent_access_respond_contact_phone_agent_id':
                op.drop_constraint('uq_contact_agent_access_respond_contact_phone_agent_id', 'contact_agent_access', type_='unique')
                break
        else:
            # If constraint not found, try dropping as index (for backwards compatibility)
            indexes = inspector.get_indexes('contact_agent_access')
            for index in indexes:
                if index['name'] == 'uq_contact_agent_access_respond_contact_phone_agent_id' and index.get('unique', False):
                    # Try to drop as constraint first
                    try:
                        op.drop_constraint('uq_contact_agent_access_respond_contact_phone_agent_id', 'contact_agent_access', type_='unique')
                    except:
                        # If that fails, drop as index
                        op.drop_index('uq_contact_agent_access_respond_contact_phone_agent_id', table_name='contact_agent_access')
                    break


def downgrade() -> None:
    # Recreate the unique constraint
    op.create_unique_constraint(
        'uq_contact_agent_access_respond_contact_phone_agent_id',
        'contact_agent_access',
        ['respond_contact_phone', 'agent_id']
    )
