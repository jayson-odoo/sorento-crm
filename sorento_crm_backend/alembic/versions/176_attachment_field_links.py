"""Attachment field linkage: template columns on attachments + per-row table.

Adds two columns to ``attachments`` to capture the upload-time template:
``target_entity_type`` (table the doc is meant to describe) and
``target_field_keys`` (JSONB array of field keys it answers).

Adds ``attachment_field_links`` (entity_type, entity_id, attachment_id,
field_key) - populated by link APIs when an attachment is linked to a
specific row, so the AI agent and FE can surface the doc per-field.

Revision ID: 176_attachment_field_links
Revises: 175_complaint_root_cause_resolution
Create Date: 2026-05-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "176_attachment_field_links"
down_revision = "175_complaint_root_cause_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("target_entity_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "attachments",
        sa.Column("target_field_keys", JSONB(), nullable=True),
    )

    op.create_table(
        "attachment_field_links",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column(
            "attachment_id",
            UUID(as_uuid=False),
            sa.ForeignKey("attachments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_key", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
    )
    op.create_index(
        "ix_afl_entity",
        "attachment_field_links",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_afl_attachment_id",
        "attachment_field_links",
        ["attachment_id"],
    )
    op.create_index(
        "uq_afl_unique",
        "attachment_field_links",
        ["entity_type", "entity_id", "attachment_id", "field_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_afl_unique", table_name="attachment_field_links")
    op.drop_index("ix_afl_attachment_id", table_name="attachment_field_links")
    op.drop_index("ix_afl_entity", table_name="attachment_field_links")
    op.drop_table("attachment_field_links")
    op.drop_column("attachments", "target_field_keys")
    op.drop_column("attachments", "target_entity_type")
