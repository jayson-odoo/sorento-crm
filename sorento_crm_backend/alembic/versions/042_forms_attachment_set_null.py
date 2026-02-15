"""Forms attachment_id: SET NULL on delete

When an attachment is permanently deleted, set forms.attachment_id to NULL.
Model already has nullable=True and ondelete=SET NULL; ensure DB constraint matches.

Revision ID: 042_forms_attach_setnull
Revises: 041_inbound_attach_setnull
Create Date: Forms attachment_id ON DELETE SET NULL

"""
from alembic import op
import sqlalchemy as sa


revision = '042_forms_attach_setnull'
down_revision = '041_inbound_attach_setnull'
branch_labels = None
depends_on = None


def _get_forms_attachment_fk_name(conn):
    result = conn.execute(
        sa.text("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.table_name = 'forms'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'attachment_id'
        """)
    )
    row = result.fetchone()
    return row[0] if row else None


def upgrade() -> None:
    conn = op.get_bind()
    fk_name = _get_forms_attachment_fk_name(conn)
    if fk_name:
        op.drop_constraint(fk_name, 'forms', type_='foreignkey')
    op.create_foreign_key(
        'forms_attachment_id_fkey',
        'forms',
        'attachments',
        ['attachment_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('forms_attachment_id_fkey', 'forms', type_='foreignkey')
    conn = op.get_bind()
    # Recreate with RESTRICT (original behavior)
    op.create_foreign_key(
        'forms_attachment_id_fkey',
        'forms',
        'attachments',
        ['attachment_id'],
        ['id'],
        ondelete='RESTRICT',
    )
