"""merge_push_and_idea_board

Revision ID: 412_merge_push_idea
Revises: 411_idea_board_perm, 411_notify_push_msg_scope
Create Date: 2026-08-24 18:44:44.162857

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '412_merge_push_idea'
down_revision = ('411_idea_board_perm', '411_notify_push_msg_scope')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
