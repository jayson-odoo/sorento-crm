"""ai prompt registry: ai_prompt_versions + ai_prompt_labels + idempotent seed

Creates the two-table prompt registry (immutable versions + movable labels) and
seeds the 9 PROMPT_KEYS at v1 from their hardcoded fallbacks, each with a
production label. Preserves any pre-existing ``ai_assistant_configs.system_prompt``
as ``agent_system`` v2 (production → v2). See
``docs/plans/PLAN-ai-assistant-prompt-registry.md`` §5/§7.

Revision ID: 258_ai_prompt_registry
Revises: 257_merge_trace_id_transporters
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.services.ai_prompt_seed import seed_prompt_registry


revision = "258_ai_prompt_registry"
down_revision = "257_merge_trace_id_transporters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())

    if "ai_prompt_versions" not in existing:
        op.create_table(
            "ai_prompt_versions",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(length=16), nullable=False, server_default="text"),
            sa.Column("template", sa.Text(), nullable=False, server_default=""),
            sa.Column("variables", postgresql.JSONB(), nullable=False, server_default="[]"),
            sa.Column("config_json", postgresql.JSONB(), nullable=True),
            sa.Column("commit_message", sa.Text(), nullable=True),
            sa.Column(
                "created_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("name", "version", name="uq_ai_prompt_versions_name_version"),
        )
        op.create_index("ix_ai_prompt_versions_name", "ai_prompt_versions", ["name"])

    if "ai_prompt_labels" not in existing:
        op.create_table(
            "ai_prompt_labels",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("label", sa.String(length=32), nullable=False),
            sa.Column(
                "version_id",
                postgresql.UUID(as_uuid=False),
                sa.ForeignKey("ai_prompt_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "updated_by",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=False),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("name", "label", name="uq_ai_prompt_labels_name_label"),
        )
        op.create_index("ix_ai_prompt_labels_name", "ai_prompt_labels", ["name"])

    # Idempotent seed (safe to re-run; never spawns duplicate versions/labels).
    seed_prompt_registry(bind)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())
    if "ai_prompt_labels" in existing:
        op.drop_index("ix_ai_prompt_labels_name", table_name="ai_prompt_labels")
        op.drop_table("ai_prompt_labels")
    if "ai_prompt_versions" in existing:
        op.drop_index("ix_ai_prompt_versions_name", table_name="ai_prompt_versions")
        op.drop_table("ai_prompt_versions")
