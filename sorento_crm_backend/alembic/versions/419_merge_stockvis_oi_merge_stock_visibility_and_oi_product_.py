"""merge stock visibility and oi product sets

Revision ID: 419_merge_stockvis_oi
Revises: 416_stock_visibility_policy, 418_merge_oi_product_sets
Create Date: 2026-08-25 20:06:25.021087

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '419_merge_stockvis_oi'
down_revision = ('416_stock_visibility_policy', '418_merge_oi_product_sets')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
