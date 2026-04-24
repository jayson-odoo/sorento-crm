"""Add AI assistant config, conversations, and governance events.

Revision ID: 144_ai_assistant_core
Revises: 143_seed_embedding_job_processor_task
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "144_ai_assistant_core"
down_revision = "143_seed_embedding_job_processor_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_assistant_configs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("provider", sa.String(length=64), server_default="openai", nullable=False),
        sa.Column("model", sa.String(length=128), server_default="gpt-4o-mini", nullable=False),
        sa.Column("temperature", sa.Integer(), server_default="0", nullable=False),
        sa.Column("system_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("enabled_tools", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("rag_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by_user_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_assistant_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_assistant_conversations_user_id", "ai_assistant_conversations", ["user_id"])
    op.create_index("ix_ai_assistant_conversations_updated_at", "ai_assistant_conversations", ["updated_at"])

    op.create_table(
        "ai_assistant_messages",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_assistant_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_assistant_messages_conversation_id", "ai_assistant_messages", ["conversation_id"])
    op.create_index("ix_ai_assistant_messages_role", "ai_assistant_messages", ["role"])

    op.create_table(
        "ai_assistant_governance_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("module_key", sa.String(length=64), nullable=True),
        sa.Column("permission_slug", sa.String(length=128), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_assistant_conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_assistant_governance_events_user_id", "ai_assistant_governance_events", ["user_id"])
    op.create_index("ix_ai_assistant_governance_events_event_type", "ai_assistant_governance_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_ai_assistant_governance_events_event_type", table_name="ai_assistant_governance_events")
    op.drop_index("ix_ai_assistant_governance_events_user_id", table_name="ai_assistant_governance_events")
    op.drop_table("ai_assistant_governance_events")
    op.drop_index("ix_ai_assistant_messages_role", table_name="ai_assistant_messages")
    op.drop_index("ix_ai_assistant_messages_conversation_id", table_name="ai_assistant_messages")
    op.drop_table("ai_assistant_messages")
    op.drop_index("ix_ai_assistant_conversations_updated_at", table_name="ai_assistant_conversations")
    op.drop_index("ix_ai_assistant_conversations_user_id", table_name="ai_assistant_conversations")
    op.drop_table("ai_assistant_conversations")
    op.drop_table("ai_assistant_configs")
