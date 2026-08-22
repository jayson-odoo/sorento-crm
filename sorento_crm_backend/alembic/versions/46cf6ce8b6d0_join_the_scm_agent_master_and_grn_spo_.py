"""join the scm agent-master and grn-spo-fm heads

Revision ID: 46cf6ce8b6d0
Revises: 357_merge_grn_spo_fm_heads, c62867691a75
Create Date: 2026-08-15 09:34:47.918732

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '46cf6ce8b6d0'
down_revision = ('357_merge_grn_spo_fm_heads', 'c62867691a75')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
