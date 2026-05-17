"""Add upload_batch_id to attachments for grouping n8n callbacks into one email.

Revision ID: 205_attachments_upload_batch_id
Revises: 204_contact_access_types_keywords
Create Date: 2026-05-17

When a user uploads multiple files in one Create Attachment submit, the FE
generates a single UUID and tags every row with it. The notification helpers
read it back and set ``data["batch_id"]`` so ``enqueue_or_merge`` collapses
the per-attachment n8n callbacks into a single coalesced email row.
"""
from alembic import op
import sqlalchemy as sa


revision = "205_attachments_upload_batch_id"
down_revision = "204_contact_access_types_keywords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("upload_batch_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_attachments_upload_batch_id",
        "attachments",
        ["upload_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_upload_batch_id", table_name="attachments")
    op.drop_column("attachments", "upload_batch_id")
