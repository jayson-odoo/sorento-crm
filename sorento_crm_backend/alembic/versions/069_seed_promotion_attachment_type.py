"""Seed attachment type for promotion uploads (code=promotion).

Revision ID: 069_promotion_attachment_type
Revises: 068_file_path_text
Create Date: 2026-02-28

"""
from alembic import op
from sqlalchemy import text


revision = "069_promotion_attachment_type"
down_revision = "068_file_path_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure an attachment type with code='promotion' exists (required for promotion uploads).
    # If a type with type_name='Promotion' already exists, set its code; otherwise insert.
    op.execute(
        text(
            "UPDATE attachment_types SET code = 'promotion' "
            "WHERE type_name = 'Promotion' AND (code IS NULL OR code != 'promotion')"
        )
    )
    op.execute(
        text(
            "INSERT INTO attachment_types (id, code, type_name, allowed_extensions, max_file_size_mb, created_at) "
            "SELECT gen_random_uuid(), 'promotion', 'Promotion', 'pdf,doc,docx,jpg,jpeg,png,gif', 50, now() AT TIME ZONE 'utc' "
            "WHERE NOT EXISTS (SELECT 1 FROM attachment_types WHERE type_name = 'Promotion')"
        )
    )


def downgrade() -> None:
    op.execute(text("UPDATE attachment_types SET code = NULL WHERE code = 'promotion'"))
