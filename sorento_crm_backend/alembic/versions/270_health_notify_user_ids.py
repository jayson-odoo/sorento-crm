"""system health: system_settings.health_notify_user_ids (individual user recipients)

Additive nullable ARRAY(String) column mirroring health_notify_role_ids, so the
digest + watchdog alerts can be sent to explicitly-picked individual users in
addition to whole roles. NULL/empty = no individual recipients (role members
and the admin fallback are unaffected).

Revision ID: 270_health_notify_user_ids
Revises: 267_health_alert_state_and_tasks
"""
from alembic import op
import sqlalchemy as sa


revision = "270_health_notify_user_ids"
down_revision = "267_health_alert_state_and_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent add: this DB may already carry the column from an earlier apply.
    op.execute(
        "ALTER TABLE system_settings "
        "ADD COLUMN IF NOT EXISTS health_notify_user_ids VARCHAR[] NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS health_notify_user_ids")
