"""Allow audit_logs.user_id to be NULL for system/public actions

Revision ID: 037_audit_logs_user_id_nullable
Revises: 036_teams_round_robin
Create Date: Allow NULL user_id (e.g. approval via public link)

"""
from alembic import op
import sqlalchemy as sa


revision = '037_audit_logs_user_id_nullable'
down_revision = '036_teams_round_robin'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow NULL so public-link approvals and other system actions can be audited without a user
    op.execute(sa.text("ALTER TABLE audit_logs ALTER COLUMN user_id DROP NOT NULL"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE audit_logs ALTER COLUMN user_id SET NOT NULL"))
