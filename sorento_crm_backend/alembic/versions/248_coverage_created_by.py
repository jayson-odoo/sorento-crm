"""notification_subscriptions.created_by_id - HoD-assigned coverage audit.

Revision ID: 248_coverage_created_by
Revises: 247_agent_team_policy_id
Create Date: 2026-06-28

Distinguishes self-service coverage (NULL / == subscriber_id) from coverage a HoD
assigned on behalf of a team member (created_by_id = the HoD). Nullable; existing
rows backfill to NULL (self-service). SET NULL on delete so removing the HoD does
not cascade-drop the coverage. See docs/plans/PLAN-hod-coverage-on-dashboard.md.
"""
from alembic import op
import sqlalchemy as sa


revision = "248_coverage_created_by"
down_revision = "247_agent_team_policy_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_subscriptions",
        sa.Column("created_by_id", sa.String(), nullable=True),
    )
    op.create_foreign_key(
        "fk_notification_subscriptions_created_by_id",
        "notification_subscriptions",
        "users",
        ["created_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_notification_subscriptions_created_by_id",
        "notification_subscriptions",
        type_="foreignkey",
    )
    op.drop_column("notification_subscriptions", "created_by_id")
