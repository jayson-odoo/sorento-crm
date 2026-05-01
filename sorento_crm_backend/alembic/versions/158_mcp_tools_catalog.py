"""MCP tool catalog + per-call access log.

Revision ID: 158_mcp_tools_catalog
Revises: 157_lookup_sets
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "158_mcp_tools_catalog"
down_revision = "157_lookup_sets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_tools",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("module_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("http_path", sa.Text(), nullable=False),
        sa.Column("http_method", sa.Text(), nullable=False, server_default="GET"),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("access_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_seen_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tool_name", name="uq_mcp_tools_tool_name"),
    )
    op.create_index("ix_mcp_tools_module_key", "mcp_tools", ["module_key"])
    op.create_index("ix_mcp_tools_is_active", "mcp_tools", ["is_active"])
    op.create_index("ix_mcp_tools_agent_id", "mcp_tools", ["agent_id"])

    op.create_table(
        "mcp_access_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("contact_external_id", sa.Text(), nullable=True),
        sa.Column("respond_contact_id", sa.Text(), nullable=True),
        sa.Column("respond_workspace_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("matched_agent_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_mcp_access_log_ts", "mcp_access_log", ["ts"])
    op.create_index("ix_mcp_access_log_tool_name", "mcp_access_log", ["tool_name"])


def downgrade() -> None:
    op.drop_index("ix_mcp_access_log_tool_name", table_name="mcp_access_log")
    op.drop_index("ix_mcp_access_log_ts", table_name="mcp_access_log")
    op.drop_table("mcp_access_log")

    op.drop_index("ix_mcp_tools_agent_id", table_name="mcp_tools")
    op.drop_index("ix_mcp_tools_is_active", table_name="mcp_tools")
    op.drop_index("ix_mcp_tools_module_key", table_name="mcp_tools")
    op.drop_table("mcp_tools")
