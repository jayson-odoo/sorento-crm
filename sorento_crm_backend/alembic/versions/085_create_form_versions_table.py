"""Create form_versions table.

The Form model has a versions relationship to FormVersion; the table was missing,
causing UndefinedTable when loading or deleting forms.

Revision ID: 085_create_form_versions
Revises: 084_form_sections_section_order
Create Date: 2026-03-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "085_create_form_versions"
down_revision = "084_form_sections_section_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("form_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("forms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("structure", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_form_versions_form_id", "form_versions", ["form_id"])
    op.create_index(
        "uq_form_versions_form_id_version_number",
        "form_versions",
        ["form_id", "version_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_form_versions_form_id_version_number", table_name="form_versions")
    op.drop_index("ix_form_versions_form_id", table_name="form_versions")
    op.drop_table("form_versions")
