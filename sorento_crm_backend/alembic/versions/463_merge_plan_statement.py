"""merge plan-owned statement with main

Revision ID: 463_merge_plan_statement
Revises: 454_plan_owned_statement, 459_outstanding_from_so
Create Date: 2026-09-03 01:06:23.552867

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '463_merge_plan_statement'
down_revision = ('454_plan_owned_statement', '459_outstanding_from_so')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
