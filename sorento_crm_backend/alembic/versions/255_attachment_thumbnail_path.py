"""add thumbnail_path to attachments (grid thumbnail perf)

Stores the CDN base URL of a ~320px thumbnail object generated at upload /
backfill, served to the Files grid so it paints small images instead of full-
resolution originals. See docs/plans/PLAN-attachment-grid-thumbnails.md.

Revision ID: 255_attachment_thumbnail_path
Revises: 253_system_settings_singleton
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "255_attachment_thumbnail_path"
down_revision = "253_system_settings_singleton"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "attachments",
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("attachments", "thumbnail_path")
