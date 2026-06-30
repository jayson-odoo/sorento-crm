"""system_settings.complaint_do_delivered_notify_tiers — DB-configurable notify tiers.

Revision ID: 252_complaint_notify_tiers_setting
Revises: 251_complaint_fulfilment_orders
Create Date: 2026-07-01

Which Complaint-team tiers (Access-Agent ``complaint``, set ``complaint``) receive
the replacement-DO-delivered email/in-app. Comma list of tier numbers, default
"1,2". Replaces the env-only COMPLAINT_DO_DELIVERED_NOTIFY_TIERS so admins can
configure it from the Settings UI. See docs/plans/PLAN-complaint-do-auto-fulfilment.md.
"""
from alembic import op
import sqlalchemy as sa


revision = "252_complaint_notify_tiers_setting"
down_revision = "251_complaint_fulfilment_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "complaint_do_delivered_notify_tiers",
            sa.String(length=20),
            nullable=False,
            server_default="1,2",
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "complaint_do_delivered_notify_tiers")
