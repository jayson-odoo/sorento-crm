"""Add unique constraint on respond_contact_id and agent_id

Revision ID: 007_contact_agent_unique
Revises: 006_remove_contact_agent_unique
Create Date: 2026-01-24 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007_contact_agent_unique'
down_revision = '006_remove_contact_agent_unique'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'contact_agent_access' in inspector.get_table_names():
        # Check if the index/constraint already exists
        indexes = inspector.get_indexes('contact_agent_access')
        index_exists = any(
            idx['name'] == 'uq_contact_agent_access_respond_contact_id_agent_id' 
            for idx in indexes
        )
        
        if not index_exists:
            # First, update any NULL respond_contact_id values to have a corresponding contact
            # This ensures data integrity before adding the constraint
            op.execute(sa.text("""
                UPDATE contact_agent_access caa
                SET respond_contact_id = rc.id
                FROM respond_contacts rc
                WHERE caa.respond_contact_id IS NULL
                AND caa.respond_contact_phone = rc.phone_number
            """))
            
            # Add unique constraint on respond_contact_id and agent_id
            # Using a partial unique index to handle NULL values properly
            # PostgreSQL allows multiple NULLs in a unique constraint, but we want to enforce uniqueness
            # only when respond_contact_id is NOT NULL
            op.execute(sa.text("""
                CREATE UNIQUE INDEX uq_contact_agent_access_respond_contact_id_agent_id 
                ON contact_agent_access (respond_contact_id, agent_id) 
                WHERE respond_contact_id IS NOT NULL
            """))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'contact_agent_access' in inspector.get_table_names():
        # Drop the unique index
        op.execute(sa.text("DROP INDEX IF EXISTS uq_contact_agent_access_respond_contact_id_agent_id"))
