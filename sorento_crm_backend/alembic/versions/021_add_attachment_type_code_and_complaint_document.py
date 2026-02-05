"""Add code to attachment_types and seed complaint_document type

Revision ID: 021_attachment_type_code
Revises: 020_create_import_jobs_table
Create Date: 2026-01-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "021_attachment_type_code"
down_revision = "020_create_import_jobs_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Add code column to attachment_types (nullable, unique)
    if "attachment_types" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("attachment_types")]
        if "code" not in columns:
            op.add_column(
                "attachment_types",
                sa.Column("code", sa.String(50), nullable=True),
            )
            op.create_index(
                "ix_attachment_types_code",
                "attachment_types",
                ["code"],
                unique=True,
            )

    # Ensure complaint_document type exists: update existing "Complaint Document" row with code, or insert
    op.execute(
        text(
            "UPDATE attachment_types SET code = 'complaint_document' "
            "WHERE type_name = 'Complaint Document' AND (code IS NULL OR code != 'complaint_document')"
        )
    )
    op.execute(
        text(
            "INSERT INTO attachment_types (id, code, type_name, allowed_extensions, max_file_size_mb, created_at) "
            "SELECT gen_random_uuid(), 'complaint_document', 'Complaint Document', '*', 50, now() AT TIME ZONE 'utc' "
            "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE code = 'complaint_document')"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    if "attachment_types" in inspector.get_table_names():
        op.execute(text("DELETE FROM attachment_types WHERE code = 'complaint_document'"))

        indexes = inspector.get_indexes("attachment_types")
        if any(idx.get("name") == "ix_attachment_types_code" for idx in indexes):
            op.drop_index("ix_attachment_types_code", table_name="attachment_types")
        columns = [c["name"] for c in inspector.get_columns("attachment_types")]
        if "code" in columns:
            op.drop_column("attachment_types", "code")
