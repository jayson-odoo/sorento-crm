"""Update existing data in conversation_sla_tracking foreign keys

Revision ID: 010_update_sla_fk_data
Revises: 009_sla_tracking_fks
Create Date: 2026-01-24 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '010_update_sla_fk_data'
down_revision = '009_sla_tracking_fks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if conversation_sla_tracking table exists
    if 'conversation_sla_tracking' not in inspector.get_table_names():
        return
    
    columns = [col['name'] for col in inspector.get_columns('conversation_sla_tracking')]
    
    # Update respond_contact_id for any records that don't have it yet
    if 'respond_contact_id' in columns:
        # Migrate existing data: match by phone_number with better matching logic
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
            AND (cst.respond_contact_id IS NULL OR cst.respond_contact_id = '')
        """))
    
    # Update assigned_to_id for any records that don't have it yet
    if 'assigned_to_id' in columns:
        # First try matching by user.id (exact match)
        op.execute(sa.text("""
            UPDATE conversation_sla_tracking cst
            SET assigned_to_id = u.id
            FROM users u
            WHERE cst.assigned_to = u.id
            AND cst.assigned_to IS NOT NULL
            AND cst.assigned_to != ''
            AND (cst.assigned_to_id IS NULL OR cst.assigned_to_id = '')
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
            AND (cst.assigned_to_id IS NULL OR cst.assigned_to_id = '')
        """))
        
        # Also try matching by email (in case assigned_to contains email)
        op.execute(sa.text("""
            UPDATE conversation_sla_tracking cst
            SET assigned_to_id = u.id
            FROM users u
            WHERE cst.assigned_to = u.email
            AND cst.assigned_to IS NOT NULL
            AND cst.assigned_to != ''
            AND (cst.assigned_to_id IS NULL OR cst.assigned_to_id = '')
        """))


def downgrade() -> None:
    # This migration only updates data, no schema changes to revert
    pass
