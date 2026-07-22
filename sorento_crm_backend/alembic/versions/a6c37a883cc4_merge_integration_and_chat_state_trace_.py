"""merge integration and chat-state-trace heads

Revision ID: a6c37a883cc4
Revises: 295_chat_history_state_trace, 301_integration_references
Create Date: 2026-07-22 14:44:56.073531

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6c37a883cc4'
down_revision = ('295_chat_history_state_trace', '301_integration_references')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
