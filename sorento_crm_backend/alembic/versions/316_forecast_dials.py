"""Forecast dials: per-status probability and staleness, plus the delivery lag (S5a).

Revision ID: 316_forecast_dials
Revises: 315_sponsorship_link

Three columns, all configuration rather than data, and all nullable-or-defaulted so nothing
existing changes behaviour on deploy:

- ``statuses.win_probability`` (AC-I2) -- NULL on purpose, not 50. An unconfigured rung has
  no opinion, and inventing a default would put a number in front of management that nobody
  chose. A status with no probability contributes zero to Weighted.
- ``statuses.stale_after_days`` (AC-H4) -- per status, because a Registered project may
  fairly sit for 30 days while a Negotiating one may not sit for 7.
- ``system_settings.project_delivery_lag_months`` (AC-I3) -- seeded 30 from the client's own
  worked example. A setting, never a constant: it is a market observation and it will change
  before the code does.

``statuses`` is a CORE table shared by every entity type, so both columns are nullable and
mean nothing to the entities that ignore them.
"""
from alembic import op

revision = "316_forecast_dials"
down_revision = "315_sponsorship_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE statuses
            ADD COLUMN IF NOT EXISTS win_probability NUMERIC(5, 2),
            ADD COLUMN IF NOT EXISTS stale_after_days INTEGER;

        ALTER TABLE system_settings
            ADD COLUMN IF NOT EXISTS project_delivery_lag_months INTEGER
            NOT NULL DEFAULT 30;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE statuses
            DROP COLUMN IF EXISTS win_probability,
            DROP COLUMN IF EXISTS stale_after_days;
        ALTER TABLE system_settings
            DROP COLUMN IF EXISTS project_delivery_lag_months;
        """
    )
