"""Form SLA: notify_assignee - per-stage toggle for assignee notification.

When false, spawning the stage assigns the tracker but does NOT notify the
assignee (silent routing). NULL/true = notify (backward-compatible).
"""
from alembic import op
import sqlalchemy as sa


revision = "232_form_sla_notify_assignee"
down_revision = "231_respond_contact_cs_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "form_sla_configs",
        sa.Column(
            "notify_assignee",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("form_sla_configs", "notify_assignee")
