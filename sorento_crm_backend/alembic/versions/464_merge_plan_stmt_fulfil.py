"""merge plan-owned statement with fulfilment planning batch

Revision ID: 464_merge_plan_stmt_fulfil
Revises: 461_so_supply_decision_drafts, 463_merge_plan_statement
Create Date: 2026-09-03 12:37:24.689233

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '464_merge_plan_stmt_fulfil'
down_revision = ('461_so_supply_decision_drafts', '463_merge_plan_statement')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
