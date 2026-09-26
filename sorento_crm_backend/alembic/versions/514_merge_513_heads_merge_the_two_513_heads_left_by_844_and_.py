"""merge the two 513 heads left by #844 and #849

Revision ID: 514_merge_513_heads
Revises: 513_chatbot_parser_last_cost, 513_loading_plan_horizon_start
Create Date: 2026-09-12 21:19:47.371813

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '514_merge_513_heads'
down_revision = ('513_chatbot_parser_last_cost', '513_loading_plan_horizon_start')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
