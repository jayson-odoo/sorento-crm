"""Create conversation_frames table for n8n chatbot episodic memory.

Stores per-topic structured snapshots of n8n bot conversations. On close, a
summary is enqueued in embedding_queue (source_type='conversation_frame') so
the existing pgvector pipeline indexes it for semantic recall.

Revision ID: 201_conversation_frames
Revises: 200_transporters_table
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID


revision = "201_conversation_frames"
down_revision = "200_transporters_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_frames",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("contact_id", sa.String(128), nullable=False),
        sa.Column("space_id", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(64), nullable=True),
        sa.Column("intent", sa.String(64), nullable=True),
        sa.Column("active_entities", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("access_levels_used", ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("tools_used", ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("result_refs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("pending_request", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("last_user_message", sa.Text(), nullable=True),
        sa.Column("last_assistant_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'open'")),
        sa.Column("close_reason", sa.String(32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_activity_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "ix_conversation_frames_contact_status",
        "conversation_frames",
        ["contact_id", "status"],
    )
    op.create_index(
        "ix_conversation_frames_contact_closed_at",
        "conversation_frames",
        ["contact_id", "closed_at"],
    )
    op.create_index(
        "ix_conversation_frames_contact_space_channel",
        "conversation_frames",
        ["contact_id", "space_id", "channel"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversation_frames_contact_space_channel", table_name="conversation_frames")
    op.drop_index("ix_conversation_frames_contact_closed_at", table_name="conversation_frames")
    op.drop_index("ix_conversation_frames_contact_status", table_name="conversation_frames")
    op.drop_table("conversation_frames")
