"""Add access_levels to attachments (dealer/end user); control at attachment level.

Revision ID: 057_attachment_access_levels
Revises: 056_attachment_description
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "057_attachment_access_levels"
down_revision = "056_attachment_description"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column(
            "access_levels",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[\"dealer\",\"end_user\"]'::jsonb"),
        ),
    )
    op.create_index(
        "ix_attachments_access_levels",
        "attachments",
        ["access_levels"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_access_levels", table_name="attachments")
    op.drop_column("attachments", "access_levels")
