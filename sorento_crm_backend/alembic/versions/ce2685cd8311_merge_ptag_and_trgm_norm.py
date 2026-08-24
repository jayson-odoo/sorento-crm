"""merge_ptag_and_trgm_norm

Revision ID: ce2685cd8311
Revises: 410_trgm_norm_idx, ptag_0001
Create Date: 2026-08-24 18:40:14.253227

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ce2685cd8311'
down_revision = ('410_trgm_norm_idx', 'ptag_0001')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
