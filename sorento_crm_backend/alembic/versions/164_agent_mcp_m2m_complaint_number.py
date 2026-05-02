"""Promote AccessAgent <-> McpTool to many-to-many and add Complaint.complaint_number.

Phase 2 introduced N:1 ownership via ``mcp_tools.agent_id``. The product
direction is many-to-many: one agent can own multiple tools AND one tool can
be shared across agents. Migrate to a join table ``agent_mcp_tools``,
backfill from the existing column, then drop the FK column.

Also adds ``complaints.complaint_number`` so portal-submitted complaints
carry a stable, user-facing reference (CMP-YYYYMMDD-nnnn) like
purchase_requests/sponsorship_forms/stock_inquiries already do.

Revision ID: 164_agent_mcp_m2m_complaint_number
Revises: 163_storage_provider_columns
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "164_agent_mcp_m2m_complaint_number"
down_revision = "163_storage_provider_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_mcp_tools",
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("access_agents.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "tool_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("mcp_tools.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_mcp_tools_agent_id", "agent_mcp_tools", ["agent_id"])
    op.create_index("ix_agent_mcp_tools_tool_id", "agent_mcp_tools", ["tool_id"])

    op.execute(
        """
        INSERT INTO agent_mcp_tools (agent_id, tool_id)
        SELECT agent_id, id FROM mcp_tools
        WHERE agent_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    op.drop_index("ix_mcp_tools_agent_id", table_name="mcp_tools")
    with op.batch_alter_table("mcp_tools") as batch:
        batch.drop_column("agent_id")

    op.add_column(
        "complaints",
        sa.Column("complaint_number", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_complaints_complaint_number",
        "complaints",
        ["complaint_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_complaints_complaint_number", table_name="complaints")
    op.drop_column("complaints", "complaint_number")

    op.add_column(
        "mcp_tools",
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("access_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_mcp_tools_agent_id", "mcp_tools", ["agent_id"])
    op.execute(
        """
        UPDATE mcp_tools t
        SET agent_id = j.agent_id
        FROM agent_mcp_tools j
        WHERE j.tool_id = t.id
        """
    )

    op.drop_index("ix_agent_mcp_tools_tool_id", table_name="agent_mcp_tools")
    op.drop_index("ix_agent_mcp_tools_agent_id", table_name="agent_mcp_tools")
    op.drop_table("agent_mcp_tools")
