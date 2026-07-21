"""Drop MCP tool ownership + per-tool access log.

n8n took over agent/team routing, so the per-tool guard and its routing
bindings are dead. `mcp_tools` stays as a pure catalog; contact access is
enforced per-agent only via `contact_agent_access` +
`mcp_access_service.evaluate_agent`.

Drops:
- `agent_mcp_tools` — both halves: legacy ownership rows (`team_id IS NULL`)
  and per-tool team/tier routing bindings (`team_id IS NOT NULL`).
- `mcp_access_log` — the per-decision audit table. It also held the
  `access-agent:*` rows written by `evaluate_agent`; logging was dropped with
  the table by explicit decision.

Revision ID: 295_drop_mcp_tool_ownership
Revises: 294_chat_latency_percentile
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "295_drop_mcp_tool_ownership"
down_revision = "294_chat_latency_percentile"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS agent_mcp_tools CASCADE")
    op.execute("DROP TABLE IF EXISTS mcp_access_log CASCADE")


def downgrade():
    """Recreate the table shells. Row data is NOT recoverable."""
    op.create_table(
        "agent_mcp_tools",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "agent_id",
            UUID(as_uuid=False),
            sa.ForeignKey("access_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tool_id",
            UUID(as_uuid=False),
            sa.ForeignKey("mcp_tools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            UUID(as_uuid=False),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("tier", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_mcp_tools_agent_id", "agent_mcp_tools", ["agent_id"])
    op.create_index("ix_agent_mcp_tools_tool_id", "agent_mcp_tools", ["tool_id"])
    op.create_index(
        "ix_agent_mcp_tools_tool_team", "agent_mcp_tools", ["tool_id", "team_id"]
    )
    op.create_index(
        "uq_agent_mcp_tools_agent_tool_team_null",
        "agent_mcp_tools",
        ["agent_id", "tool_id"],
        unique=True,
        postgresql_where=sa.text("team_id IS NULL"),
    )
    op.create_index(
        "uq_agent_mcp_tools_agent_tool_team_not_null",
        "agent_mcp_tools",
        ["agent_id", "tool_id", "team_id"],
        unique=True,
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )

    op.create_table(
        "mcp_access_log",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("contact_external_id", sa.Text(), nullable=True),
        sa.Column("respond_contact_id", sa.Text(), nullable=True),
        sa.Column("respond_workspace_id", UUID(as_uuid=False), nullable=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("matched_agent_id", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "ts", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_mcp_access_log_ts", "mcp_access_log", ["ts"])
    op.create_index("ix_mcp_access_log_tool_name", "mcp_access_log", ["tool_name"])
