"""merge scm module chain into main

Revision ID: 9785e8947154
Revises: 273_import_source_file, 285_market_signal_sources
Create Date: 2026-07-18 02:23:04.243882

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9785e8947154'
down_revision = ('273_import_source_file', '285_market_signal_sources')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
