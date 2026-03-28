"""Add agent_code and team_set_code to conversation_sla_tracking."""
from alembic import op
import sqlalchemy as sa

revision = "121_sla_tracking_agent_team_set_codes"
down_revision = "120_sync_sla_test_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_sla_tracking",
        sa.Column("agent_code", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "conversation_sla_tracking",
        sa.Column("team_set_code", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_sla_tracking", "team_set_code")
    op.drop_column("conversation_sla_tracking", "agent_code")
