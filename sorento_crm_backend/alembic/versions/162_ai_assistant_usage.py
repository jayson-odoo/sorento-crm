"""AI assistant usage logs, wishlist clusters, and unanswered queries.

Revision ID: 162_ai_assistant_usage
Revises: 160_contact_portal_link
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.rbac.permission_registry import sync_permissions


revision = "162_ai_assistant_usage"
down_revision = "160_contact_portal_link"
branch_labels = None
depends_on = None


def _has_pgvector(bind) -> bool:
    """True when the live database has the pgvector extension enabled."""
    try:
        result = bind.execute(
            sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        return bool(result)
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    pgvector_available = _has_pgvector(bind)

    # ai_assistant_usage_logs --------------------------------------------------
    op.create_table(
        "ai_assistant_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tool_calls_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("response_time_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("was_answered", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_assistant_conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["ai_assistant_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_assistant_usage_logs_user_id", "ai_assistant_usage_logs", ["user_id"])
    op.create_index("ix_ai_assistant_usage_logs_created_at", "ai_assistant_usage_logs", ["created_at"])
    op.create_index("ix_ai_assistant_usage_logs_message_id", "ai_assistant_usage_logs", ["message_id"])

    # ai_assistant_wishlist_clusters ------------------------------------------
    cluster_columns = [
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("representative_question", sa.Text(), server_default="", nullable=False),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
    ]
    if pgvector_available:
        from pgvector.sqlalchemy import Vector  # type: ignore

        cluster_columns.append(sa.Column("representative_embedding", Vector(1536), nullable=True))
    else:
        cluster_columns.append(
            sa.Column("representative_embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
        )
    op.create_table(
        "ai_assistant_wishlist_clusters",
        *cluster_columns,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_assistant_wishlist_clusters_count", "ai_assistant_wishlist_clusters", ["count"])
    op.create_index(
        "ix_ai_assistant_wishlist_clusters_last_seen_at",
        "ai_assistant_wishlist_clusters",
        ["last_seen_at"],
    )

    # ai_assistant_unanswered_queries -----------------------------------------
    unanswered_columns = [
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.text("now()"), nullable=False),
    ]
    if pgvector_available:
        from pgvector.sqlalchemy import Vector  # type: ignore

        unanswered_columns.append(sa.Column("embedding", Vector(1536), nullable=True))
    else:
        unanswered_columns.append(
            sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
        )
    op.create_table(
        "ai_assistant_unanswered_queries",
        *unanswered_columns,
        sa.ForeignKeyConstraint(["message_id"], ["ai_assistant_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["ai_assistant_wishlist_clusters.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_ai_assistant_unanswered_queries_message_id"),
    )
    op.create_index(
        "ix_ai_assistant_unanswered_queries_cluster_id",
        "ai_assistant_unanswered_queries",
        ["cluster_id"],
    )
    op.create_index(
        "ix_ai_assistant_unanswered_queries_created_at",
        "ai_assistant_unanswered_queries",
        ["created_at"],
    )

    # Sync permissions registry (no-op if no new slugs were registered).
    session = Session(bind=bind)
    try:
        sync_permissions(session, created_by_user_id=None)
    finally:
        session.close()


def downgrade() -> None:
    op.drop_index(
        "ix_ai_assistant_unanswered_queries_created_at",
        table_name="ai_assistant_unanswered_queries",
    )
    op.drop_index(
        "ix_ai_assistant_unanswered_queries_cluster_id",
        table_name="ai_assistant_unanswered_queries",
    )
    op.drop_table("ai_assistant_unanswered_queries")
    op.drop_index(
        "ix_ai_assistant_wishlist_clusters_last_seen_at",
        table_name="ai_assistant_wishlist_clusters",
    )
    op.drop_index(
        "ix_ai_assistant_wishlist_clusters_count",
        table_name="ai_assistant_wishlist_clusters",
    )
    op.drop_table("ai_assistant_wishlist_clusters")
    op.drop_index("ix_ai_assistant_usage_logs_message_id", table_name="ai_assistant_usage_logs")
    op.drop_index("ix_ai_assistant_usage_logs_created_at", table_name="ai_assistant_usage_logs")
    op.drop_index("ix_ai_assistant_usage_logs_user_id", table_name="ai_assistant_usage_logs")
    op.drop_table("ai_assistant_usage_logs")
