"""Merge the customer importer chain with the portal-revisions chain.

Both branched off `6f86dd016850`, so merging main into this feature branch left two
alembic heads and CI's bootstrap refused to stamp: "Multiple heads are present". This
revision joins them and does nothing else - a merge revision has no DDL by construction.

Revision ID: 885010d94677
Revises: 355_customers_length_drift, 7cc13b71908c
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '885010d94677'
down_revision = ('355_customers_length_drift', '7cc13b71908c')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
