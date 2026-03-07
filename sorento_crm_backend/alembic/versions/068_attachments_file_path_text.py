"""Widen attachments.file_path for CloudFront signed URLs.

Revision ID: 068_file_path_text
Revises: 067_outgoing_mails_perm
Create Date: CloudFront signed URLs exceed VARCHAR(500)

"""
from alembic import op
import sqlalchemy as sa


revision = "068_file_path_text"
down_revision = "067_outgoing_mails_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "attachments",
        "file_path",
        existing_type=sa.String(500),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "attachments",
        "file_path",
        existing_type=sa.Text(),
        type_=sa.String(500),
        existing_nullable=False,
    )
