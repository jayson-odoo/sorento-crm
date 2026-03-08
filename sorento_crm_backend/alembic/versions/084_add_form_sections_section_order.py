"""Add section_order to form_sections.

The FormSection model expects form_sections.section_order; add the column
so ORM queries (e.g. on form delete) no longer raise UndefinedColumn.

Revision ID: 084_form_sections_section_order
Revises: 083_form_sections_section_name
Create Date: 2026-03-08

"""
from alembic import op
import sqlalchemy as sa


revision = "084_form_sections_section_order"
down_revision = "083_form_sections_section_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "form_sections",
        sa.Column("section_order", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("form_sections", "section_order")
