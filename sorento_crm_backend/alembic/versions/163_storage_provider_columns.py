"""Add storage_provider columns for the S3 -> Cloudflare R2 transition.

Each attachment row records which backend hosts its file so reads (preview,
download, presigned URL) can dispatch to the correct provider during the
period when both S3/CloudFront and R2/Cloudflare CDN serve traffic. New rows
default to 's3' so existing behaviour is unchanged until the migration script
flips them to 'r2'.

Revision ID: 163_storage_provider_columns
Revises: 162_ai_assistant_usage
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "163_storage_provider_columns"
down_revision = "162_ai_assistant_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column(
            "storage_provider",
            sa.String(length=16),
            nullable=False,
            server_default="s3",
        ),
    )
    op.create_index(
        "ix_attachments_storage_provider",
        "attachments",
        ["storage_provider"],
    )

    op.add_column(
        "users",
        sa.Column(
            "avatar_storage_provider",
            sa.String(length=16),
            nullable=False,
            server_default="s3",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_storage_provider")
    op.drop_index("ix_attachments_storage_provider", table_name="attachments")
    op.drop_column("attachments", "storage_provider")
