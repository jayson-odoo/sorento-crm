"""Create pgvector embedding pipeline tables.

Revision ID: 142_pgvector_embedding_pipeline
Revises: 141_attachments_created_at
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "142_pgvector_embedding_pipeline"
down_revision = "141_attachments_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "embedding_queue",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.UUID(), nullable=True),
        sa.Column("rq_job_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_embedding_queue_status_available_at",
        "embedding_queue",
        ["status", "available_at"],
        unique=False,
    )
    op.create_index("ix_embedding_queue_source", "embedding_queue", ["source_type", "source_id"], unique=False)
    op.create_index("ix_embedding_queue_correlation_id", "embedding_queue", ["correlation_id"], unique=False)

    op.create_table(
        "embedding_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_key", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("visibility_scope", sa.String(length=64), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_embedding_documents_source", "embedding_documents", ["source_type", "source_id"], unique=False)
    op.create_index(
        "ix_embedding_documents_source_hash",
        "embedding_documents",
        ["source_type", "source_id", "source_hash"],
        unique=False,
    )

    op.create_table(
        "embedding_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("embedded_at", sa.DateTime(timezone=False), nullable=False, server_default=sa.text("now()")),
        sa.Column("superseded_at", sa.DateTime(timezone=False), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["embedding_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_embedding_chunks_source_current",
        "embedding_chunks",
        ["source_type", "source_id", "is_current"],
        unique=False,
    )
    op.create_index(
        "ix_embedding_chunks_model_current",
        "embedding_chunks",
        ["model_name", "model_version", "is_current"],
        unique=False,
    )
    op.create_index(
        "uq_embedding_chunks_current",
        "embedding_chunks",
        ["source_type", "source_id", "model_name", "model_version", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_embedding_chunks_embedding_hnsw
        ON embedding_chunks USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embedding_chunks_embedding_hnsw")
    op.drop_index("uq_embedding_chunks_current", table_name="embedding_chunks")
    op.drop_index("ix_embedding_chunks_model_current", table_name="embedding_chunks")
    op.drop_index("ix_embedding_chunks_source_current", table_name="embedding_chunks")
    op.drop_table("embedding_chunks")
    op.drop_index("ix_embedding_documents_source_hash", table_name="embedding_documents")
    op.drop_index("ix_embedding_documents_source", table_name="embedding_documents")
    op.drop_table("embedding_documents")
    op.drop_index("ix_embedding_queue_correlation_id", table_name="embedding_queue")
    op.drop_index("ix_embedding_queue_source", table_name="embedding_queue")
    op.drop_index("ix_embedding_queue_status_available_at", table_name="embedding_queue")
    op.drop_table("embedding_queue")
