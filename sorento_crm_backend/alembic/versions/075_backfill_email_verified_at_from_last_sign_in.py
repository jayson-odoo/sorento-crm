"""Backfill email_verified_at for signed-in users.

Revision ID: 075_backfill_email_verified_at
Revises: 074_user_agent_access
Create Date: 2026-03-06
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "075_backfill_email_verified_at"
down_revision = "074_user_agent_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # If a user has signed in, treat them as verified for now.
    op.execute(
        """
        UPDATE users
        SET email_verified_at = last_sign_in_at
        WHERE email_verified_at IS NULL
          AND last_sign_in_at IS NOT NULL
        """
    )


def downgrade() -> None:
    # Irreversible without historical data; no-op.
    pass

