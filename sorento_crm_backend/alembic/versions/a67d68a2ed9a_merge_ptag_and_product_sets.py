"""merge_ptag_and_product_sets

Revision ID: a67d68a2ed9a
Revises: 415_merge_pset_pushidea, ptag_0001
Create Date: 2026-08-24 21:29:23.214313

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a67d68a2ed9a'
down_revision = ('415_merge_pset_pushidea', 'ptag_0001')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
