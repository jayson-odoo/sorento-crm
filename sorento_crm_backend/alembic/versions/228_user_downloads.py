"""User downloads table: async-generated exports (e.g. complaint PDFs) for the
"My Downloads" drawer.

Revision ID: 228_user_downloads
Revises: 227_complaint_resolved_status
Create Date: 2026-06-09
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "228_user_downloads"
down_revision = "227_complaint_resolved_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_downloads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("source_entity_type", sa.String(length=50), nullable=True),
        sa.Column("source_entity_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("storage_provider", sa.String(length=10), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.func.now()),
        sa.Column("ready_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index("ix_user_downloads_user_id", "user_downloads", ["user_id"])
    op.create_index("ix_user_downloads_status", "user_downloads", ["status"])
    op.create_index("ix_user_downloads_created_at", "user_downloads", ["created_at"])
    op.create_index("ix_user_downloads_source_entity_id", "user_downloads", ["source_entity_id"])


def downgrade() -> None:
    op.drop_index("ix_user_downloads_source_entity_id", table_name="user_downloads")
    op.drop_index("ix_user_downloads_created_at", table_name="user_downloads")
    op.drop_index("ix_user_downloads_status", table_name="user_downloads")
    op.drop_index("ix_user_downloads_user_id", table_name="user_downloads")
    op.drop_table("user_downloads")
