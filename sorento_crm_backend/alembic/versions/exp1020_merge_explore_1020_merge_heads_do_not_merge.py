"""EXPLORE-1020 merge heads (DO NOT MERGE)

Revision ID: exp1020_merge
Revises: spec_bare_size_0001, adp_0001_pcs_attach_delete
Create Date: 2026-10-20 14:07:02.588878

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'exp1020_merge'
down_revision = ('spec_bare_size_0001', 'adp_0001_pcs_attach_delete')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
