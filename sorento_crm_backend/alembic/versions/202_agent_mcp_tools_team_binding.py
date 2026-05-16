"""Extend agent_mcp_tools with per-tool team binding (team_id + tier).

Lets a single tool be routed to a specific team within an agent's portfolio
rather than fanning out to every team the agent belongs to (AgentTeam x
agent_mcp_tools cartesian product). Backwards-compatible: rows with team_id
NULL keep the legacy "agent owns tool, route via AgentTeam" semantics.

Revision ID: 202_agent_mcp_tools_team_binding
Revises: 201_conversation_frames
Create Date: 2026-05-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "202_agent_mcp_tools_team_binding"
down_revision = "201_conversation_frames"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_mcp_tools",
        sa.Column("id", UUID(as_uuid=False), nullable=True),
    )
    op.execute(
        "UPDATE agent_mcp_tools SET id = gen_random_uuid() WHERE id IS NULL"
    )
    op.alter_column("agent_mcp_tools", "id", nullable=False)

    op.add_column(
        "agent_mcp_tools",
        sa.Column(
            "team_id",
            UUID(as_uuid=False),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_mcp_tools",
        sa.Column("tier", sa.Integer(), nullable=True),
    )

    op.execute("ALTER TABLE agent_mcp_tools DROP CONSTRAINT agent_mcp_tools_pkey")
    op.create_primary_key("agent_mcp_tools_pkey", "agent_mcp_tools", ["id"])

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
    op.create_index(
        "ix_agent_mcp_tools_tool_team",
        "agent_mcp_tools",
        ["tool_id", "team_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_mcp_tools_tool_team", table_name="agent_mcp_tools")
    op.drop_index(
        "uq_agent_mcp_tools_agent_tool_team_not_null",
        table_name="agent_mcp_tools",
    )
    op.drop_index(
        "uq_agent_mcp_tools_agent_tool_team_null",
        table_name="agent_mcp_tools",
    )

    op.execute(
        "DELETE FROM agent_mcp_tools t USING agent_mcp_tools t2 "
        "WHERE t.ctid < t2.ctid AND t.agent_id = t2.agent_id AND t.tool_id = t2.tool_id"
    )
    op.execute("ALTER TABLE agent_mcp_tools DROP CONSTRAINT agent_mcp_tools_pkey")
    op.create_primary_key(
        "agent_mcp_tools_pkey", "agent_mcp_tools", ["agent_id", "tool_id"]
    )

    op.drop_column("agent_mcp_tools", "tier")
    op.drop_column("agent_mcp_tools", "team_id")
    op.drop_column("agent_mcp_tools", "id")
