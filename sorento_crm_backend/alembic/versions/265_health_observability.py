"""system health observability: audit_logs.contact_id + system_settings health cols

Two additive, nullable/defaulted changes (WS system-health-observability):

1. ``audit_logs.contact_id`` (nullable, indexed) — attributes portal/public-link
   writes to the acting contact (respond_contacts.id). NULL for staff writes and
   for the `system` automation principal. Display resolves contact_id -> contact
   name BEFORE the user_id -> staff / "System" fallback.

2. ``system_settings`` health-digest + watchdog config columns. Singleton table
   (migration 253 enforces one row); these carry defaults so the existing row is
   valid immediately. Recipients are role ids (ARRAY) mirroring notify_*_role_ids.

Revision ID: 265_health_observability
Revises: 269_form_handling_lock
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "265_health_observability"
down_revision = "269_form_handling_lock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. audit_logs.contact_id (idempotent add + index)
    op.add_column(
        "audit_logs",
        sa.Column("contact_id", sa.String(length=100), nullable=True),
    )
    op.create_index("ix_audit_logs_contact_id", "audit_logs", ["contact_id"])

    # 2. system_settings health observability config
    op.add_column(
        "system_settings",
        sa.Column("health_digest_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "system_settings",
        sa.Column("health_alerts_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "system_settings",
        sa.Column("health_notify_role_ids", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("health_integration_fail_threshold", sa.Integer(), nullable=False, server_default="10"),
    )
    op.add_column(
        "system_settings",
        sa.Column("health_audit_volume_floor", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "health_audit_volume_floor")
    op.drop_column("system_settings", "health_integration_fail_threshold")
    op.drop_column("system_settings", "health_notify_role_ids")
    op.drop_column("system_settings", "health_alerts_enabled")
    op.drop_column("system_settings", "health_digest_enabled")
    op.drop_index("ix_audit_logs_contact_id", table_name="audit_logs")
    op.drop_column("audit_logs", "contact_id")
