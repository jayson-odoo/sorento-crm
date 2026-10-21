"""EXPLORE-1021B merge ccmp_0001 and lean_0001 (exploratory)

Revision ID: ex1021b_merge
Revises: ccmp_0001_composer_switch, lean_0001_parser_reasoning
Create Date: 2026-10-21 12:07:12.396122

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ex1021b_merge'
down_revision = ('ccmp_0001_composer_switch', 'lean_0001_parser_reasoning')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
