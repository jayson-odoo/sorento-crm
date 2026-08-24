"""Enforce system_settings is a singleton (≤ 1 row).

Revision ID: 253_system_settings_singleton
Revises: 252_complaint_notify_tiers_setting
Create Date: 2026-07-01

system_settings is company-wide config and must have exactly one row, but the
table had accumulated duplicates. `db.query(SystemSetting).first()` has no
ORDER BY, so reads and writes could non-deterministically hit different rows  - 
silently breaking every settings save. Collapse to one row (keep the earliest
by ctid) and add a unique index on a constant expression so a second row can
never be inserted again.
"""
from alembic import op


revision = "253_system_settings_singleton"
down_revision = "252_complaint_notify_tiers_setting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Defensive dedupe (no-op when already a singleton): keep one physical row.
    op.execute(
        """
        DELETE FROM system_settings
        WHERE ctid NOT IN (SELECT min(ctid) FROM system_settings)
        """
    )
    # Singleton guard: unique index on a constant -> at most one row.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_system_settings_singleton "
        "ON system_settings ((true))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_system_settings_singleton")
