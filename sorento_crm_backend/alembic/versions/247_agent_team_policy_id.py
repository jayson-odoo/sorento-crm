"""agent_teams.policy_id — backend-owned conversation SLA policy binding.

Revision ID: 247_agent_team_policy_id
Revises: 246_sla_tier_hours_decimal
Create Date: 2026-06-24

Conversation SLA policy is resolved server-side from (agent_id, team_set_code) via
this column instead of being supplied by n8n. Nullable: existing rows backfill by
admin (UI) before the n8n policy_id fallback is removed. FK RESTRICT so a bound
policy cannot be deleted. See docs/plans/PLAN-conversation-policy-binding.md.
"""
from alembic import op
import sqlalchemy as sa


revision = "247_agent_team_policy_id"
down_revision = "246_sla_tier_hours_decimal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_teams",
        sa.Column("policy_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_teams_policy_id",
        "agent_teams",
        "sla_policies",
        ["policy_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_agent_teams_policy_id", "agent_teams", ["policy_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_teams_policy_id", table_name="agent_teams")
    op.drop_constraint("fk_agent_teams_policy_id", "agent_teams", type_="foreignkey")
    op.drop_column("agent_teams", "policy_id")
