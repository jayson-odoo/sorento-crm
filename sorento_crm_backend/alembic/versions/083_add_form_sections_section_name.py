"""Add section_name to form_sections.

The FormSection model expects form_sections.section_name; add the column
so ORM queries (e.g. on form delete) no longer raise UndefinedColumn.

Revision ID: 083_form_sections_section_name
Revises: 082_import_job_seconds
Create Date: 2026-03-08

"""
from alembic import op
import sqlalchemy as sa


revision = "083_form_sections_section_name"
down_revision = "082_import_job_seconds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "form_sections",
        sa.Column("section_name", sa.String(255), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("form_sections", "section_name")
