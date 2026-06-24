"""Coverage redirect toggle: notification_subscriptions.redirect_assignments.

Revision ID: 245_coverage_redirect_assignments
Revises: 244_sla_extend_deadline
Create Date: 2026-06-24

Adds the per-coverage mode flag backing PLAN-coverage-redirect-assignment:

- redirect_assignments = True  → auto-assign the target's future SLA tasks to the
  subscriber (assignment + escalation redirected); the subscriber must be the SOLE
  active coverer for that target.
- redirect_assignments = False → notify-only (original behaviour): fan-out coverage
  notification copies, subscriber takes over manually; multiple notify-only coverers
  per target allowed.

server_default 'false' → EXISTING coverage rows stay notify-only, so the change is
fully backward-compatible. Idempotent and reversible.
"""
from alembic import op
import sqlalchemy as sa


revision = "245_coverage_redirect_assignments"
down_revision = "244_sla_extend_deadline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_subscriptions",
        sa.Column(
            "redirect_assignments",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_subscriptions", "redirect_assignments")
