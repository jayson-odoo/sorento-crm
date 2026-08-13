"""merge portal revisions with scm purchasing

Revision ID: 7cc13b71908c
Revises: d475a0f72146, 6f86dd016850
Create Date: 2026-08-13 11:16:55.911168

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7cc13b71908c'
down_revision = ('d475a0f72146', '6f86dd016850')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
