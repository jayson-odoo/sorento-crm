"""merge portal revisions with company aware routing

Revision ID: d475a0f72146
Revises: cac36dbd46ab, portal_rev_0001
Create Date: 2026-08-13 07:12:25.522213

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd475a0f72146'
down_revision = ('cac36dbd46ab', 'portal_rev_0001')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
