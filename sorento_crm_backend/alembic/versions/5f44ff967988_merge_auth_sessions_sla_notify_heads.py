"""merge auth-sessions + sla-notify heads

Revision ID: 5f44ff967988
Revises: 237_user_sessions, a1b2c3d4e5f6
Create Date: 2026-06-21 19:54:36.379811

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f44ff967988'
down_revision = ('237_user_sessions', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
