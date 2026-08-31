"""merge ptag chain with autocount sweep

Revision ID: 447_merge_ptag_ac
Revises: 445_autocount_grant_sweep, 446_merge_ptag_s6b
Create Date: 2026-08-31 01:36:15.698834

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '447_merge_ptag_ac'
down_revision = ('445_autocount_grant_sweep', '446_merge_ptag_s6b')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
