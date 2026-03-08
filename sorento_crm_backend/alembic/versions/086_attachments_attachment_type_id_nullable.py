"""Allow attachments.attachment_type_id to be NULL (SET NULL when attachment type is deleted).

The Attachment model already has nullable=True and ondelete=SET NULL; the DB column
was NOT NULL, so deleting an attachment type failed when PostgreSQL tried to set
attachment_type_id to NULL. Make the column nullable and ensure FK uses ON DELETE SET NULL.

Revision ID: 086_attachments_type_nullable
Revises: 085_create_form_versions
Create Date: 2026-03-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "086_attachments_type_nullable"
down_revision = "085_create_form_versions"
branch_labels = None
depends_on = None


def _get_attachments_type_fk_name(conn):
    result = conn.execute(
        sa.text("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.table_name = 'attachments'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND kcu.column_name = 'attachment_type_id'
        """)
    )
    row = result.fetchone()
    return row[0] if row else None


def upgrade() -> None:
    # 1. Allow NULL so ON DELETE SET NULL can run
    op.alter_column(
        "attachments",
        "attachment_type_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=True,
    )
    # 2. Ensure FK has ON DELETE SET NULL (drop and recreate)
    conn = op.get_bind()
    fk_name = _get_attachments_type_fk_name(conn)
    if fk_name:
        op.drop_constraint(fk_name, "attachments", type_="foreignkey")
    op.create_foreign_key(
        "attachments_attachment_type_id_fkey",
        "attachments",
        "attachment_types",
        ["attachment_type_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("attachments_attachment_type_id_fkey", "attachments", type_="foreignkey")
    op.create_foreign_key(
        "attachments_attachment_type_id_fkey",
        "attachments",
        "attachment_types",
        ["attachment_type_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # Revert to NOT NULL (will fail if any rows have NULL attachment_type_id)
    op.alter_column(
        "attachments",
        "attachment_type_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=False,
    )
