"""Remove respond_contact_phone and respond_contact_name columns from conversation_sla_tracking

Revision ID: 011_remove_contact_columns
Revises: 010_update_sla_fk_data
Create Date: 2026-01-24 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_remove_contact_columns'
down_revision = '010_update_sla_fk_data'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if conversation_sla_tracking table exists
    if 'conversation_sla_tracking' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
    
    # Drop respond_contact_name column if it exists
    if 'respond_contact_name' in columns:
        op.drop_column('conversation_sla_tracking', 'respond_contact_name')
    
    # Drop respond_contact_phone column if it exists
    if 'respond_contact_phone' in columns:
        # First, ensure all records have respond_contact_id populated from phone number
        # This is a safety check - the previous migration should have done this
        try:
            op.execute(sa.text("""
                UPDATE conversation_sla_tracking cst
                SET respond_contact_id = rc.id
                FROM respond_contacts rc
                WHERE cst.respond_contact_phone = rc.phone_number
                AND cst.respond_contact_id IS NULL
                AND cst.respond_contact_phone IS NOT NULL
                AND cst.respond_contact_phone != ''
            """))
        except Exception:
            pass  # Ignore if update fails
        
        # Drop any unique constraint/index on respond_contact_phone if it exists
        # Check for unique constraints first
        constraints = inspector.get_unique_constraints('conversation_sla_tracking')
        for constraint in constraints:
            if 'respond_contact_phone' in constraint.get('column_names', []):
                try:
                    op.drop_constraint(constraint['name'], 'conversation_sla_tracking', type_='unique')
                except Exception:
                    try:
                        op.execute(sa.text(f"DROP INDEX IF EXISTS {constraint['name']}"))
                    except Exception:
                        pass
        
        # Check for indexes
        indexes = inspector.get_indexes('conversation_sla_tracking')
        for index in indexes:
            if index['name'] == 'uq_conversation_sla_tracking_respond_contact_phone':
                try:
                    op.drop_index(index['name'], table_name='conversation_sla_tracking')
                except Exception:
                    pass
        
        # Drop the column
        op.drop_column('conversation_sla_tracking', 'respond_contact_phone')


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'conversation_sla_tracking' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
    
    # Re-add respond_contact_phone column
    if 'respond_contact_phone' not in columns:
        op.add_column('conversation_sla_tracking', 
                     sa.Column('respond_contact_phone', sa.Text(), nullable=True))
        
        # Populate from respond_contacts table via respond_contact_id
        op.execute(sa.text("""
            UPDATE conversation_sla_tracking cst
            SET respond_contact_phone = rc.phone_number
            FROM respond_contacts rc
            WHERE cst.respond_contact_id = rc.id
            AND cst.respond_contact_phone IS NULL
        """))
        
        # Recreate unique constraint
        op.create_unique_constraint(
            'uq_conversation_sla_tracking_respond_contact_phone',
            'conversation_sla_tracking',
            ['respond_contact_phone']
        )
    
    # Re-add respond_contact_name column
    if 'respond_contact_name' not in columns:
        op.add_column('conversation_sla_tracking', 
                     sa.Column('respond_contact_name', sa.Text(), nullable=True))
        
        # Populate from respond_contacts table via respond_contact_id
        op.execute(sa.text("""
            UPDATE conversation_sla_tracking cst
            SET respond_contact_name = rc.name
            FROM respond_contacts rc
            WHERE cst.respond_contact_id = rc.id
            AND cst.respond_contact_name IS NULL
        """))
