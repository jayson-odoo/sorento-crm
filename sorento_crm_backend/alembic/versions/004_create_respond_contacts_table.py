"""Create respond_contacts table and update contact_agent_access

Revision ID: 004_create_respond_contacts_table
Revises: 003_rename_contact_id_to_phone
Create Date: 2026-01-24 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_respond_contacts'
down_revision = '003_rename_contact_id_to_phone'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    # Create respond_contacts table
    # If table exists with wrong schema (from failed migration), drop it first
    if 'respond_contacts' in tables:
        columns = {col['name']: col for col in inspector.get_columns('respond_contacts')}
        if 'id' in columns:
            # Check if id column type is UUID (wrong) instead of TEXT
            id_col = columns['id']
            # Get the actual database type
            result = connection.execute(sa.text("""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'respond_contacts' AND column_name = 'id'
            """)).fetchone()
            if result and 'uuid' in result[0].lower():
                # Table exists with wrong type, drop it to recreate with correct type
                # (This is safe since migration failed before inserting data)
                op.drop_table('respond_contacts')
                tables.remove('respond_contacts')  # Update local list
    
    if 'respond_contacts' not in tables:
        op.create_table(
            'respond_contacts',
            sa.Column('id', sa.Text(), primary_key=True, server_default=sa.text('gen_random_uuid()::text')),
            sa.Column('phone_number', sa.Text(), nullable=False),
            sa.Column('name', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.Column('created_by', sa.Text(), nullable=True),
        )
        
        # Create unique constraint on phone_number
        op.create_unique_constraint('uq_respond_contacts_phone_number', 'respond_contacts', ['phone_number'])
        
        # Create index on phone_number
        op.create_index('ix_respond_contacts_phone_number', 'respond_contacts', ['phone_number'])
    
    # Update contact_agent_access table
    if 'contact_agent_access' in tables:
        columns = [col['name'] for col in inspector.get_columns('contact_agent_access')]
        
        # Add respond_contact_id column if it doesn't exist
        if 'respond_contact_id' not in columns:
            op.add_column('contact_agent_access', 
                         sa.Column('respond_contact_id', sa.Text(), nullable=True))
        
        # Create foreign key constraint
        try:
            op.create_foreign_key(
                'fk_contact_agent_access_respond_contact_id',
                'contact_agent_access',
                'respond_contacts',
                ['respond_contact_id'],
                ['id'],
                ondelete='CASCADE'
            )
        except Exception:
            # Foreign key might already exist, ignore
            pass
        
        # Create index on respond_contact_id
        indexes = [idx['name'] for idx in inspector.get_indexes('contact_agent_access')]
        if 'ix_contact_agent_access_respond_contact_id' not in indexes:
            op.create_index('ix_contact_agent_access_respond_contact_id', 
                          'contact_agent_access', ['respond_contact_id'])
        
        # Migrate existing data: create contacts from unique phone numbers
        # This will create respond_contacts entries for all unique phone numbers
        # First, ensure we have the table created before inserting
        op.execute("""
            INSERT INTO respond_contacts (id, phone_number, name, created_at, updated_at)
            SELECT DISTINCT ON (respond_contact_phone)
                gen_random_uuid()::text,
                respond_contact_phone,
                MAX(respond_contact_name) FILTER (WHERE respond_contact_name IS NOT NULL AND respond_contact_name != ''),
                MIN(created_at),
                MAX(COALESCE(updated_at, created_at))
            FROM contact_agent_access
            WHERE respond_contact_phone IS NOT NULL 
              AND respond_contact_phone != ''
            GROUP BY respond_contact_phone
            ON CONFLICT (phone_number) DO UPDATE
            SET name = COALESCE(EXCLUDED.name, respond_contacts.name),
                updated_at = GREATEST(respond_contacts.updated_at, EXCLUDED.updated_at)
        """)
        
        # Update contact_agent_access to link to respond_contacts
        op.execute("""
            UPDATE contact_agent_access caa
            SET respond_contact_id = rc.id
            FROM respond_contacts rc
            WHERE caa.respond_contact_phone = rc.phone_number
              AND caa.respond_contact_id IS NULL
        """)


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'contact_agent_access' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('contact_agent_access')]
        indexes = [idx['name'] for idx in inspector.get_indexes('contact_agent_access')]
        constraints = [c['name'] for c in inspector.get_foreign_keys('contact_agent_access')]
        
        # Drop foreign key
        if 'fk_contact_agent_access_respond_contact_id' in constraints:
            op.drop_constraint('fk_contact_agent_access_respond_contact_id', 'contact_agent_access', type_='foreignkey')
        
        # Drop index
        if 'ix_contact_agent_access_respond_contact_id' in indexes:
            op.drop_index('ix_contact_agent_access_respond_contact_id', table_name='contact_agent_access')
        
        # Drop column
        if 'respond_contact_id' in columns:
            op.drop_column('contact_agent_access', 'respond_contact_id')
    
    # Drop respond_contacts table
    if 'respond_contacts' in inspector.get_table_names():
        op.drop_table('respond_contacts')
