"""Create user_agent_access table.

Revision ID: 074_user_agent_access
Revises: 073_assign_new_contacts
Create Date: 2026-02-21

The UserAgentAccess model exists in code but this table was never created by a migration,
causing errors when listing users (e.g. high pagination) or permanently deleting users.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "074_user_agent_access"
down_revision = "073_assign_new_contacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "user_agent_access" in inspector.get_table_names():
        return
    op.create_table(
        "user_agent_access",
        sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(100), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=False), sa.ForeignKey("access_agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("valid_from", sa.DateTime(timezone=False), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_agent_access_user_id", "user_agent_access", ["user_id"])
    op.create_index("ix_user_agent_access_agent_id", "user_agent_access", ["agent_id"])
    op.create_unique_constraint(
        "uq_user_agent_access_user_id_agent_id",
        "user_agent_access",
        ["user_id", "agent_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "user_agent_access" not in inspector.get_table_names():
        return
    op.drop_constraint("uq_user_agent_access_user_id_agent_id", "user_agent_access", type_="unique")
    op.drop_index("ix_user_agent_access_agent_id", table_name="user_agent_access")
    op.drop_index("ix_user_agent_access_user_id", table_name="user_agent_access")
    op.drop_table("user_agent_access")
