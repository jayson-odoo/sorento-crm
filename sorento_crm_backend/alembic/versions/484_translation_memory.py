"""Translation memory (R15, purchasing consolidation batch, lane C).

One row per Chinese -> English phrase, read by ``translation_service.translate`` before
any AI call and written to on both a manual edit and an AI fill. Not company-scoped -
see ``app.models.translation_memory`` for why.

Revision ID: 484_translation_memory
Revises: 483_supplier_doc_aliases
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "484_translation_memory"
down_revision = "483_supplier_doc_aliases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "translation_memory",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_lang", sa.String(8), nullable=False, server_default="zh"),
        sa.Column("target_lang", sa.String(8), nullable=False, server_default="en"),
        sa.Column("target_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "created_by",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("source IN ('manual', 'ai')", name="ck_translation_memory_source"),
        sa.UniqueConstraint(
            "source_text", "source_lang", "target_lang", name="uq_translation_memory_phrase"
        ),
    )
    op.create_index(
        "ix_translation_memory_updated_at", "translation_memory", ["updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_translation_memory_updated_at", table_name="translation_memory")
    op.drop_table("translation_memory")
