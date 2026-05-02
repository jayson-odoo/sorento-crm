"""Add is_default to respond_workspaces.

Adds an ``is_default`` boolean (default false) and a partial unique index
ensuring only one workspace can be flagged default at a time. Used by the
contact sync flow (scheduled + manual) to assign new contacts to a tenant
default when no explicit workspace is provided.

Revision ID: 165_respond_workspace_is_default
Revises: 164_agent_mcp_m2m_complaint_number
Create Date: 2026-05-02
"""

from alembic import op
import sqlalchemy as sa


revision = "165_respond_workspace_is_default"
down_revision = "164_agent_mcp_m2m_complaint_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "respond_workspaces",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        "uq_respond_workspaces_one_default",
        "respond_workspaces",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_respond_workspaces_one_default",
        table_name="respond_workspaces",
    )
    op.drop_column("respond_workspaces", "is_default")
