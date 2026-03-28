"""Replace agent_code (text) with agent_id FK to access_agents on conversation_sla_tracking."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "122_sla_tracking_agent_id_fk"
down_revision = "121_sla_tracking_agent_team_set_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the new agent_id column (UUID FK, nullable)
    op.add_column(
        "conversation_sla_tracking",
        sa.Column("agent_id", UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversation_sla_tracking_agent_id",
        "conversation_sla_tracking",
        "access_agents",
        ["agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_conversation_sla_tracking_agent_id",
        "conversation_sla_tracking",
        ["agent_id"],
    )

    # 2. Migrate existing text codes → UUIDs from access_agents
    op.execute("""
        UPDATE conversation_sla_tracking t
        SET agent_id = (
            SELECT id FROM access_agents WHERE code = t.agent_code
        )
        WHERE t.agent_code IS NOT NULL AND t.agent_code <> ''
    """)

    # 3. Drop the old agent_code column
    op.drop_column("conversation_sla_tracking", "agent_code")


def downgrade() -> None:
    # Re-add agent_code and restore values from the FK relationship
    op.add_column(
        "conversation_sla_tracking",
        sa.Column("agent_code", sa.String(length=100), nullable=True),
    )
    op.execute("""
        UPDATE conversation_sla_tracking t
        SET agent_code = (
            SELECT code FROM access_agents WHERE id = t.agent_id
        )
        WHERE t.agent_id IS NOT NULL
    """)
    op.drop_index("ix_conversation_sla_tracking_agent_id", table_name="conversation_sla_tracking")
    op.drop_constraint("fk_conversation_sla_tracking_agent_id", "conversation_sla_tracking", type_="foreignkey")
    op.drop_column("conversation_sla_tracking", "agent_id")
